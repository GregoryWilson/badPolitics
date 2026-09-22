from sqlalchemy import select
from app.models.entities import (
    Bill, EvidenceEntity, LegislativeEntityLink, EntityRelationship, CorrelationFinding,
)
from app.services.graph import normalize_name

ID_KEYS = {
    "bioguide",
    "fec_candidate_id",
    "fec_committee_id",
    "lda_client_id",
    "lda_registrant_id",
}

def _aliases(entity: EvidenceEntity):
    values=set()
    metadata=entity.metadata_json or {}
    aliases=metadata.get("aliases") or []
    if isinstance(aliases,str):
        aliases=[aliases]
    for value in aliases:
        if value:
            values.add(normalize_name(str(value)))
    return values

def _shared_external_id(a: EvidenceEntity, b: EvidenceEntity):
    left=a.external_ids or {}
    right=b.external_ids or {}
    for key in ID_KEYS:
        if left.get(key) and right.get(key) and str(left[key])==str(right[key]):
            return key,str(left[key])
    return None

def _match(a: EvidenceEntity, b: EvidenceEntity):
    shared=_shared_external_id(a,b)
    if shared:
        key,value=shared
        return "external_id",1.0,f"Both entities share {key}={value}."
    if a.normalized_name and a.normalized_name==b.normalized_name:
        return "exact_name",0.95,f"Canonical names normalize to the same value: {a.normalized_name}."
    aa=_aliases(a); ba=_aliases(b)
    if b.normalized_name in aa or a.normalized_name in ba or aa.intersection(ba):
        return "alias",0.85,"An explicitly stored alias links the two entity names."
    return None

def correlate_bill(db, bill_id:int):
    bill=db.get(Bill,bill_id)
    if not bill:
        raise ValueError("Bill not found")

    linked_ids=set(db.scalars(
        select(LegislativeEntityLink.entity_id).where(LegislativeEntityLink.bill_id==bill_id)
    ).all())
    legislative_entities=[db.get(EvidenceEntity,i) for i in linked_ids]

    relationship_entity_ids=set()
    rels=db.scalars(select(EntityRelationship)).all()
    for r in rels:
        relationship_entity_ids.add(r.source_entity_id)
        relationship_entity_ids.add(r.target_entity_id)
    candidates=[db.get(EvidenceEntity,i) for i in relationship_entity_ids if i not in linked_ids]

    created=[]
    for left in legislative_entities:
        if not left:
            continue
        for right in candidates:
            if not right or left.id==right.id:
                continue
            match=_match(left,right)
            if not match:
                continue
            basis,confidence,evidence=match
            existing=db.scalar(select(CorrelationFinding).where(
                CorrelationFinding.bill_id==bill_id,
                CorrelationFinding.legislative_entity_id==left.id,
                CorrelationFinding.matched_entity_id==right.id,
                CorrelationFinding.match_basis==basis,
            ))
            if existing:
                continue
            row=CorrelationFinding(
                bill_id=bill_id,
                legislative_entity_id=left.id,
                matched_entity_id=right.id,
                match_basis=basis,
                confidence=confidence,
                evidence=evidence,
                metadata_json={
                    "legislative_entity_type":left.entity_type,
                    "matched_entity_type":right.entity_type,
                },
            )
            db.add(row)
            db.flush()
            created.append(row.id)
    db.commit()
    return correlations_for_bill(db,bill_id,created_ids=created)

def correlations_for_bill(db,bill_id:int,created_ids=None):
    rows=db.scalars(
        select(CorrelationFinding)
        .where(CorrelationFinding.bill_id==bill_id)
        .order_by(CorrelationFinding.confidence.desc(),CorrelationFinding.id)
    ).all()
    created_ids=set(created_ids or [])
    out=[]
    for row in rows:
        left=db.get(EvidenceEntity,row.legislative_entity_id)
        right=db.get(EvidenceEntity,row.matched_entity_id)
        rels=db.scalars(select(EntityRelationship).where(
            ((EntityRelationship.source_entity_id==right.id) | (EntityRelationship.target_entity_id==right.id))
        )).all()
        out.append({
            "id":row.id,
            "new":row.id in created_ids,
            "match_basis":row.match_basis,
            "confidence":row.confidence,
            "evidence":row.evidence,
            "legislative_entity":{
                "id":left.id,
                "type":left.entity_type,
                "name":left.canonical_name,
                "external_ids":left.external_ids,
            },
            "matched_entity":{
                "id":right.id,
                "type":right.entity_type,
                "name":right.canonical_name,
                "external_ids":right.external_ids,
            },
            "external_relationships":[{
                "id":r.id,
                "relation_type":r.relation_type,
                "source_entity_id":r.source_entity_id,
                "target_entity_id":r.target_entity_id,
                "source_system":r.source_system,
                "source_url":r.source_url,
                "observed_on":r.observed_on,
                "evidence":r.evidence,
                "metadata":r.metadata_json,
            } for r in rels],
            "metadata":row.metadata_json,
        })
    return {"bill_id":bill_id,"correlation_count":len(out),"correlations":out}
