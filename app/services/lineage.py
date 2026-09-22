import difflib
import re
from datetime import date
from sqlalchemy import select, delete

from app.models.entities import (
    Bill, BillVersion, Section, Amendment, ProvisionLineage, AmendmentAttribution,
)
from app.services.diffing import unified

WORD_RE=re.compile(r"\b[A-Za-z][A-Za-z0-9'-]{2,}\b")
STOPWORDS={
    "the","and","for","that","with","from","this","shall","may","must","are","was","were",
    "into","under","section","subsection","paragraph","bill","act","amendment","amended",
    "relating","provide","providing","other","such","each","any","all","not",
}

def _date_value(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None

def _version_key(version):
    parsed=_date_value(version.issued_on)
    return (0,parsed,version.id) if parsed else (1,date.max,version.id)

def _tokens(text):
    return {
        token.casefold()
        for token in WORD_RE.findall(text or "")
        if token.casefold() not in STOPWORDS
    }

def _amendment_date(amendment):
    raw=amendment.raw_json or {}
    latest=raw.get("latestAction") or {}
    return _date_value(
        latest.get("actionDate")
        or raw.get("submittedDate")
        or raw.get("proposedDate")
        or raw.get("date")
    )

def _amendment_people(amendment):
    raw=amendment.raw_json or {}
    people=[]
    candidates=[]
    if isinstance(raw.get("sponsors"),list):
        candidates.extend(raw["sponsors"])
    if raw.get("sponsor"):
        candidates.append(raw["sponsor"])
    for item in candidates:
        if isinstance(item,dict):
            name=item.get("fullName") or item.get("name") or item.get("bioguideId")
        else:
            name=str(item)
        if name and name not in people:
            people.append(name)
    return people

def _amendment_text(amendment):
    raw=amendment.raw_json or {}
    parts=[
        amendment.description,
        amendment.latest_action,
        raw.get("purpose"),
        raw.get("description"),
    ]
    return " ".join(str(x) for x in parts if x)

def _candidate_attributions(amendments,from_version,to_version,new_text):
    from_date=_date_value(from_version.issued_on) if from_version else None
    to_date=_date_value(to_version.issued_on)
    changed_tokens=_tokens(new_text)
    candidates=[]
    for amendment in amendments:
        amendment_date=_amendment_date(amendment)
        temporal=False
        if amendment_date and to_date:
            temporal=amendment_date<=to_date and (not from_date or amendment_date>=from_date)
        amendment_tokens=_tokens(_amendment_text(amendment))
        overlap=len(changed_tokens.intersection(amendment_tokens))
        denominator=max(1,min(len(changed_tokens),len(amendment_tokens)))
        token_overlap=overlap/denominator

        if temporal and token_overlap>=0.08:
            confidence=min(0.85,0.50+token_overlap)
            evidence="Amendment action date falls between the compared bill versions and its descriptive text overlaps the changed provision."
            candidates.append((amendment,confidence,evidence,token_overlap,"temporal_text_overlap"))
        elif temporal:
            candidates.append((
                amendment,0.40,
                "Amendment action date falls between the compared bill versions, but descriptive text does not materially overlap the provision.",
                token_overlap,"temporal_only",
            ))
        elif token_overlap>=0.25:
            candidates.append((
                amendment,min(0.65,0.35+token_overlap),
                "Amendment descriptive text overlaps the changed provision, but version-date ordering does not establish temporal attribution.",
                token_overlap,"text_overlap_only",
            ))
    return sorted(candidates,key=lambda x:x[1],reverse=True)[:10]

def build_lineage(db,bill_id:int):
    bill=db.get(Bill,bill_id)
    if not bill:
        raise ValueError("Bill not found")
    versions=db.scalars(
        select(BillVersion).where(BillVersion.bill_id==bill_id)
    ).all()
    versions=sorted(versions,key=_version_key)
    if not versions:
        raise ValueError("Bill has no stored text versions")

    amendments=db.scalars(
        select(Amendment).where(Amendment.bill_id==bill_id)
    ).all()

    db.execute(delete(AmendmentAttribution).where(
        AmendmentAttribution.lineage_id.in_(
            select(ProvisionLineage.id).where(ProvisionLineage.bill_id==bill_id)
        )
    ))
    db.execute(delete(ProvisionLineage).where(ProvisionLineage.bill_id==bill_id))
    db.flush()

    previous={}
    rows=[]
    for version in versions:
        current_sections=db.scalars(
            select(Section)
            .where(Section.version_id==version.id)
            .order_by(Section.ordinal)
        ).all()
        current={s.section_number:s for s in current_sections}

        if not previous:
            for number,section in current.items():
                row=ProvisionLineage(
                    bill_id=bill_id,
                    section_number=number,
                    from_version_id=None,
                    to_version_id=version.id,
                    event_type="introduced",
                    similarity=None,
                    old_text=None,
                    new_text=section.text,
                    diff_text=None,
                    metadata_json={"to_version":version.version_code},
                )
                db.add(row); db.flush(); rows.append(row)
            previous=current
            continue

        prior_version=versions[versions.index(version)-1]
        all_numbers=sorted(set(previous).union(current))
        for number in all_numbers:
            old=previous.get(number)
            new=current.get(number)
            if old is None and new is not None:
                event_type="introduced"
                similarity=None
                diff_text=None
            elif old is not None and new is None:
                event_type="removed"
                similarity=None
                diff_text=None
            else:
                similarity=round(difflib.SequenceMatcher(None,old.text,new.text).ratio(),4)
                if old.text==new.text:
                    continue
                event_type="modified"
                diff_text=unified(
                    old.text,new.text,
                    old_name=f"{prior_version.version_code}:section-{number}",
                    new_name=f"{version.version_code}:section-{number}",
                )

            row=ProvisionLineage(
                bill_id=bill_id,
                section_number=number,
                from_version_id=prior_version.id,
                to_version_id=version.id,
                event_type=event_type,
                similarity=similarity,
                old_text=old.text if old else None,
                new_text=new.text if new else None,
                diff_text=diff_text,
                metadata_json={
                    "from_version":prior_version.version_code,
                    "to_version":version.version_code,
                },
            )
            db.add(row); db.flush(); rows.append(row)

            if event_type in {"introduced","modified"} and new is not None:
                for amendment,confidence,evidence,overlap,basis in _candidate_attributions(
                    amendments,prior_version,version,new.text
                ):
                    db.add(AmendmentAttribution(
                        lineage_id=row.id,
                        amendment_id=amendment.id,
                        attribution_type="candidate",
                        confidence=confidence,
                        evidence=evidence,
                        metadata_json={
                            "basis":basis,
                            "token_overlap":round(overlap,4),
                            "amendment_people":_amendment_people(amendment),
                        },
                    ))
        previous=current

    db.commit()
    return lineage_result(db,bill_id)

def lineage_result(db,bill_id:int):
    bill=db.get(Bill,bill_id)
    if not bill:
        raise ValueError("Bill not found")
    versions={v.id:v for v in db.scalars(select(BillVersion).where(BillVersion.bill_id==bill_id)).all()}
    amendments={a.id:a for a in db.scalars(select(Amendment).where(Amendment.bill_id==bill_id)).all()}
    rows=db.scalars(
        select(ProvisionLineage)
        .where(ProvisionLineage.bill_id==bill_id)
        .order_by(ProvisionLineage.to_version_id,ProvisionLineage.section_number)
    ).all()
    result=[]
    for row in rows:
        attrs=db.scalars(
            select(AmendmentAttribution)
            .where(AmendmentAttribution.lineage_id==row.id)
            .order_by(AmendmentAttribution.confidence.desc())
        ).all()
        result.append({
            "id":row.id,
            "section_number":row.section_number,
            "event_type":row.event_type,
            "similarity":row.similarity,
            "from_version":{
                "id":row.from_version_id,
                "code":versions[row.from_version_id].version_code if row.from_version_id else None,
                "issued_on":versions[row.from_version_id].issued_on if row.from_version_id else None,
            },
            "to_version":{
                "id":row.to_version_id,
                "code":versions[row.to_version_id].version_code,
                "issued_on":versions[row.to_version_id].issued_on,
            },
            "old_text":row.old_text,
            "new_text":row.new_text,
            "diff":row.diff_text,
            "candidate_amendments":[{
                "attribution_id":attr.id,
                "amendment_id":attr.amendment_id,
                "amendment_type":amendments[attr.amendment_id].amendment_type,
                "amendment_number":amendments[attr.amendment_id].amendment_number,
                "description":amendments[attr.amendment_id].description,
                "latest_action":amendments[attr.amendment_id].latest_action,
                "source_url":amendments[attr.amendment_id].source_url,
                "confidence":attr.confidence,
                "evidence":attr.evidence,
                "metadata":attr.metadata_json,
            } for attr in attrs],
            "metadata":row.metadata_json,
        })
    return {
        "bill_id":bill_id,
        "event_count":len(result),
        "events":result,
        "interpretation_note":"Provision lineage records when section text first appears, changes, or disappears. Amendment links are candidate associations unless an authoritative source explicitly identifies the amendment as the source of the change.",
    }
