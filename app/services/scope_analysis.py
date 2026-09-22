import math
import re
from collections import Counter
from sqlalchemy import select, delete

from app.models.entities import Bill, BillVersion, Section, ProvisionLineage, ScopeFinding

WORD_RE=re.compile(r"\b[A-Za-z][A-Za-z0-9'-]{2,}\b")
STOPWORDS={
    "the","and","for","that","with","from","this","shall","may","must","are","was","were",
    "into","under","section","subsection","paragraph","bill","act","amendment","amended",
    "relating","provide","provides","providing","other","such","each","any","all","not",
    "thereof","therein","thereunder","including","means","term","state","federal","law",
    "chapter","code","article","title","part","division","applicable","effective","date",
}

def _tokens(text):
    return [
        token.casefold()
        for token in WORD_RE.findall(text or "")
        if token.casefold() not in STOPWORDS and not token.isdigit()
    ]

def _metadata_scope(metadata):
    metadata=metadata or {}
    values=[]
    subjects=metadata.get("subjects")
    if isinstance(subjects,list):
        values.extend(str(x) for x in subjects if x)
    policy=metadata.get("policyArea")
    if isinstance(policy,dict):
        values.extend(str(x) for x in policy.values() if x)
    elif policy:
        values.append(str(policy))
    for key in ("summary","subject","subjectsTopTerms"):
        value=metadata.get(key)
        if isinstance(value,list):
            values.extend(str(x) for x in value if x)
        elif isinstance(value,str):
            values.append(value)
    return " ".join(values)

def _idf(counters):
    count=len(counters)
    df=Counter()
    for counter in counters:
        for term in counter:
            df[term]+=1
    return {term:math.log((1+count)/(1+freq))+1 for term,freq in df.items()}

def _vector(counter,idf):
    if not counter:
        return {}
    total=sum(counter.values()) or 1
    return {term:(freq/total)*idf.get(term,1.0) for term,freq in counter.items()}

def _cosine(a,b):
    if not a or not b:
        return 0.0
    dot=sum(value*b.get(term,0.0) for term,value in a.items())
    na=math.sqrt(sum(v*v for v in a.values()))
    nb=math.sqrt(sum(v*v for v in b.values()))
    if not na or not nb:
        return 0.0
    return dot/(na*nb)

def _centroid(vectors):
    if not vectors:
        return {}
    out=Counter()
    for vector in vectors:
        out.update(vector)
    return {term:value/len(vectors) for term,value in out.items()}

def _top_divergent_terms(section_vector,reference_vector,limit=8):
    ranked=[]
    for term,value in section_vector.items():
        delta=value-reference_vector.get(term,0.0)
        if delta>0:
            ranked.append((delta,term))
    ranked.sort(reverse=True)
    return [term for _,term in ranked[:limit]]

def _percentile(values,p):
    values=sorted(values)
    if not values:
        return 0.0
    if len(values)==1:
        return values[0]
    pos=(len(values)-1)*p
    lo=int(math.floor(pos)); hi=int(math.ceil(pos))
    if lo==hi:
        return values[lo]
    return values[lo]*(hi-pos)+values[hi]*(pos-lo)

def analyze_scope_sections(title,metadata,sections):
    eligible=[s for s in sections if s.section_number!="ROOT" and len(_tokens(s.text))>=35]
    if len(eligible)<4:
        return []

    anchor_text=" ".join(x for x in [title or "",_metadata_scope(metadata)] if x)
    anchor_counter=Counter(_tokens(anchor_text))
    counters=[Counter(_tokens((s.heading or "")+" "+s.text)) for s in eligible]
    idf=_idf(counters+([anchor_counter] if anchor_counter else []))
    vectors=[_vector(c,idf) for c in counters]
    anchor_vector=_vector(anchor_counter,idf) if anchor_counter else {}

    peer_scores=[]
    anchor_scores=[]
    for i,vector in enumerate(vectors):
        peer=_centroid([v for j,v in enumerate(vectors) if j!=i])
        peer_scores.append(_cosine(vector,peer))
        anchor_scores.append(_cosine(vector,anchor_vector) if anchor_vector else None)

    peer_cutoff=min(0.20,_percentile(peer_scores,0.25))
    findings=[]
    for i,section in enumerate(eligible):
        peer=peer_scores[i]
        anchor=anchor_scores[i]
        low_peer=peer<=peer_cutoff
        low_anchor=anchor is None or anchor<=0.12
        if not (low_peer and low_anchor):
            continue
        reference=_centroid([v for j,v in enumerate(vectors) if j!=i])
        divergent=_top_divergent_terms(vectors[i],reference)
        distance=max(0.0,1.0-peer)
        anchor_distance=(1.0-anchor) if anchor is not None else 0.5
        confidence=min(0.95,0.55+(distance*0.20)+(anchor_distance*0.15))
        statement=(
            "Section subject matter is unusually distant from both the stated bill scope and neighboring sections."
            if anchor is not None
            else "Section subject matter is unusually distant from the dominant subject matter of neighboring sections; stated-scope metadata was unavailable."
        )
        findings.append({
            "section":section,
            "category":"scope_outlier",
            "confidence":round(confidence,4),
            "anchor_similarity":round(anchor,4) if anchor is not None else None,
            "peer_similarity":round(peer,4),
            "statement":statement,
            "evidence":"Divergent terms: "+(", ".join(divergent) if divergent else "none identified")+".",
            "metadata":{
                "divergent_terms":divergent,
                "peer_cutoff":round(peer_cutoff,4),
                "eligible_section_count":len(eligible),
            },
        })
    return findings

def run_scope_analysis(db,bill_id:int):
    bill=db.get(Bill,bill_id)
    if not bill:
        raise ValueError("Bill not found")
    latest=db.scalar(
        select(BillVersion)
        .where(BillVersion.bill_id==bill_id)
        .order_by(BillVersion.issued_on.desc(),BillVersion.id.desc())
    )
    if not latest:
        raise ValueError("Bill has no stored text version")
    sections=db.scalars(
        select(Section).where(Section.version_id==latest.id).order_by(Section.ordinal)
    ).all()
    candidates=analyze_scope_sections(bill.title,bill.metadata_json,sections)

    later_sections={
        row.section_number
        for row in db.scalars(
            select(ProvisionLineage).where(
                ProvisionLineage.bill_id==bill_id,
                ProvisionLineage.from_version_id.is_not(None),
                ProvisionLineage.event_type=="introduced",
            )
        ).all()
    }

    db.execute(delete(ScopeFinding).where(ScopeFinding.bill_id==bill_id))
    for item in candidates:
        section=item["section"]
        category="late_scope_outlier" if section.section_number in later_sections else item["category"]
        statement=item["statement"]
        if category=="late_scope_outlier":
            statement="Later-added section is also a semantic scope outlier relative to the bill's stated and dominant subject matter."
        db.add(ScopeFinding(
            bill_id=bill_id,
            version_id=latest.id,
            section_id=section.id,
            category=category,
            confidence=min(0.98,item["confidence"]+(0.08 if category=="late_scope_outlier" else 0)),
            anchor_similarity=item["anchor_similarity"],
            peer_similarity=item["peer_similarity"],
            statement=statement,
            evidence=item["evidence"],
            metadata_json={**item["metadata"],"section_number":section.section_number,"heading":section.heading},
        ))
    db.commit()
    return scope_analysis_result(db,bill_id)

def scope_analysis_result(db,bill_id:int):
    bill=db.get(Bill,bill_id)
    if not bill:
        raise ValueError("Bill not found")
    rows=db.scalars(
        select(ScopeFinding)
        .where(ScopeFinding.bill_id==bill_id)
        .order_by(ScopeFinding.confidence.desc(),ScopeFinding.id)
    ).all()
    sections={s.id:s for s in db.scalars(select(Section).join(BillVersion).where(BillVersion.bill_id==bill_id)).all()}
    out=[]
    for row in rows:
        section=sections.get(row.section_id)
        out.append({
            "id":row.id,
            "category":row.category,
            "confidence":row.confidence,
            "anchor_similarity":row.anchor_similarity,
            "peer_similarity":row.peer_similarity,
            "section_id":row.section_id,
            "section_number":section.section_number if section else row.metadata_json.get("section_number"),
            "heading":section.heading if section else row.metadata_json.get("heading"),
            "statement":row.statement,
            "evidence":row.evidence,
            "metadata":row.metadata_json,
        })
    return {
        "bill_id":bill_id,
        "finding_count":len(out),
        "findings":out,
        "interpretation_note":"Scope mismatch is a semantic outlier signal, not a conclusion that a provision is improper or an unrelated rider. Broad omnibus bills and specialized drafting language can create legitimate outliers.",
    }