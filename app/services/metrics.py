import re
from collections import Counter
from sqlalchemy import select, func
from app.models.entities import (
    Bill, BillVersion, Section, Finding, BillSponsor, Amendment,
    LegislativeEntityLink, EvidenceEntity,
)
from app.services.diffing import summary as diff_summary

_AMOUNT_RE = re.compile(r"\$\s*([0-9][0-9,]*(?:\.\d+)?)\s*(thousand|million|billion)?", re.I)
_MULTIPLIERS = {None:1, "thousand":1_000, "million":1_000_000, "billion":1_000_000_000}

def parse_money_text(value: str) -> float | None:
    m=_AMOUNT_RE.search(value or "")
    if not m:
        return None
    number=float(m.group(1).replace(",",""))
    unit=m.group(2).lower() if m.group(2) else None
    return number * _MULTIPLIERS[unit]

def bill_metrics(db, bill_id: int):
    bill=db.get(Bill,bill_id)
    if not bill:
        raise ValueError("Bill not found")

    versions=db.scalars(
        select(BillVersion).where(BillVersion.bill_id==bill_id).order_by(BillVersion.id.asc())
    ).all()
    latest=versions[-1] if versions else None

    sections=db.scalars(
        select(Section).where(Section.version_id==latest.id).order_by(Section.ordinal)
    ).all() if latest else []

    findings=db.scalars(
        select(Finding).where(Finding.version_id==latest.id)
    ).all() if latest else []

    counts=Counter(f.kind for f in findings)
    explicit_amounts=[]
    for finding in findings:
        if finding.kind=="money":
            raw=(finding.metadata_json or {}).get("amount_text") or finding.evidence
            value=parse_money_text(raw)
            if value is not None:
                explicit_amounts.append(value)

    sponsors=db.scalars(select(BillSponsor).where(BillSponsor.bill_id==bill_id)).all()
    sponsor_counts=Counter(s.role for s in sponsors)
    amendment_count=db.scalar(
        select(func.count()).select_from(Amendment).where(Amendment.bill_id==bill_id)
    ) or 0

    entity_rows=db.execute(
        select(LegislativeEntityLink.link_type, EvidenceEntity.entity_type)
        .join(EvidenceEntity, LegislativeEntityLink.entity_id==EvidenceEntity.id)
        .where(LegislativeEntityLink.bill_id==bill_id)
    ).all()
    entity_link_counts=Counter(link_type for link_type,_ in entity_rows)
    entity_type_counts=Counter(entity_type for _,entity_type in entity_rows)

    change=None
    if len(versions)>=2:
        old,new=versions[-2],versions[-1]
        change=diff_summary(old.text,new.text)

    return {
        "bill_id":bill.id,
        "jurisdiction":bill.jurisdiction,
        "congress":bill.congress,
        "bill_type":bill.bill_type,
        "bill_number":bill.bill_number,
        "title":bill.title,
        "latest_version":latest.version_code if latest else None,
        "version_count":len(versions),
        "section_count":len(sections),
        "word_count":sum(len(s.text.split()) for s in sections),
        "finding_count":len(findings),
        "finding_counts":dict(sorted(counts.items())),
        "money":{
            "explicit_amount_mentions":len(explicit_amounts),
            "explicit_amount_sum":sum(explicit_amounts),
            "largest_explicit_amount":max(explicit_amounts) if explicit_amounts else 0,
            "unspecified_spending_mentions":counts.get("unspecified_spending",0),
        },
        "policy_mechanics":{
            "exemption_mentions":counts.get("exemption",0),
            "retroactivity_mentions":counts.get("retroactivity",0),
            "grandfather_mentions":counts.get("grandfather",0),
            "enforcement_limit_mentions":counts.get("enforcement_limit",0),
            "cross_reference_density_flags":counts.get("cross_reference_density",0),
        },
        "specificity":{
            "named_geography_links":entity_link_counts.get("named_geography",0),
            "beneficiary_class_links":entity_link_counts.get("potential_beneficiary_class",0),
            "entity_types":dict(sorted(entity_type_counts.items())),
        },
        "legislative_activity":{
            "sponsor_count":sponsor_counts.get("sponsor",0),
            "cosponsor_count":sponsor_counts.get("cosponsor",0),
            "amendment_count":amendment_count,
            "latest_version_change":change,
        },
    }
