import re
from sqlalchemy import select, or_
from app.models.entities import (
    Bill, BillVersion, BillSponsor, Section,
    EvidenceEntity, LegislativeEntityLink, EntityRelationship,
)

BENEFICIARY_PATTERNS = [
    re.compile(r"\b(trade associations?)\b", re.I),
    re.compile(r"\b(small businesses?)\b", re.I),
    re.compile(r"\b(manufacturers?)\b", re.I),
    re.compile(r"\b(producers?)\b", re.I),
    re.compile(r"\b(eligible (?:entities|recipients|applicants))\b", re.I),
    re.compile(r"\b(nonprofit organizations?)\b", re.I),
    re.compile(r"\b(tribal (?:governments|organizations|entities))\b", re.I),
    re.compile(r"\b(institutions of higher education)\b", re.I),
]

GEO_PATTERN = re.compile(
    r"\b((?:City|Town|County|Parish|Borough|District) of (?:[A-Z][A-Za-z'-]*\s*){1,6}|"
    r"(?:[A-Z][A-Za-z'-]*\s+){1,6}(?:County|Parish|Borough|District))\b"
)

def normalize_name(value: str) -> str:
    return " ".join(value.casefold().split())

def get_or_create_entity(db, entity_type: str, canonical_name: str, external_ids=None, metadata=None):
    normalized = normalize_name(canonical_name)
    entity = db.scalar(select(EvidenceEntity).where(
        EvidenceEntity.entity_type == entity_type,
        EvidenceEntity.normalized_name == normalized,
    ))
    if entity:
        if external_ids:
            entity.external_ids = {**(entity.external_ids or {}), **external_ids}
        if metadata:
            entity.metadata_json = {**(entity.metadata_json or {}), **metadata}
        return entity
    entity = EvidenceEntity(
        entity_type=entity_type,
        canonical_name=canonical_name.strip(),
        normalized_name=normalized,
        external_ids=external_ids or {},
        metadata_json=metadata or {},
    )
    db.add(entity)
    db.flush()
    return entity

def link_entity(db, bill_id, entity, link_type, evidence, section_id=None, source_url=None,
                confidence=1.0, extraction_method="deterministic", metadata=None):
    existing = db.scalar(select(LegislativeEntityLink).where(
        LegislativeEntityLink.bill_id == bill_id,
        LegislativeEntityLink.section_id == section_id,
        LegislativeEntityLink.entity_id == entity.id,
        LegislativeEntityLink.link_type == link_type,
    ))
    if existing:
        return existing
    link = LegislativeEntityLink(
        bill_id=bill_id,
        section_id=section_id,
        entity_id=entity.id,
        link_type=link_type,
        evidence=evidence[:4000],
        source_url=source_url,
        confidence=confidence,
        extraction_method=extraction_method,
        metadata_json=metadata or {},
    )
    db.add(link)
    return link

def sync_bill_graph(db, bill_id: int):
    bill = db.get(Bill, bill_id)
    if not bill:
        raise ValueError("Bill not found")

    sponsors = db.scalars(select(BillSponsor).where(BillSponsor.bill_id == bill_id)).all()
    for sponsor in sponsors:
        entity = get_or_create_entity(
            db, "person", sponsor.full_name,
            external_ids={"bioguide": sponsor.bioguide_id} if sponsor.bioguide_id else {},
            metadata={"party": sponsor.party, "state": sponsor.state, "district": sponsor.district},
        )
        link_entity(
            db, bill_id, entity, sponsor.role,
            evidence=f"Official Congress.gov {sponsor.role} record for {sponsor.full_name}.",
            confidence=1.0, extraction_method="congress_api",
        )

    latest = db.scalar(select(BillVersion).where(BillVersion.bill_id == bill_id).order_by(BillVersion.issued_on.desc(), BillVersion.id.desc()))
    sections = db.scalars(select(Section).where(Section.version_id == latest.id)).all() if latest else []

    for section in sections:
        for pattern in BENEFICIARY_PATTERNS:
            for match in pattern.finditer(section.text):
                name = match.group(1)
                entity = get_or_create_entity(db, "beneficiary_class", name)
                link_entity(
                    db, bill_id, entity, "potential_beneficiary_class",
                    evidence=section.text[max(0, match.start()-180):match.end()+260],
                    section_id=section.id,
                    source_url=latest.source_url,
                    confidence=0.70,
                    metadata={"version": latest.version_code, "section": section.section_number},
                )
        for match in GEO_PATTERN.finditer(section.text):
            name = match.group(1).strip()
            entity = get_or_create_entity(db, "geography", name)
            link_entity(
                db, bill_id, entity, "named_geography",
                evidence=section.text[max(0, match.start()-180):match.end()+260],
                section_id=section.id,
                source_url=latest.source_url,
                confidence=0.85,
                metadata={"version": latest.version_code, "section": section.section_number},
            )

    db.commit()
    return graph_for_bill(db, bill_id)

def graph_for_bill(db, bill_id: int):
    rows = db.execute(
        select(LegislativeEntityLink, EvidenceEntity, Section)
        .join(EvidenceEntity, LegislativeEntityLink.entity_id == EvidenceEntity.id)
        .outerjoin(Section, LegislativeEntityLink.section_id == Section.id)
        .where(LegislativeEntityLink.bill_id == bill_id)
        .order_by(LegislativeEntityLink.confidence.desc(), EvidenceEntity.canonical_name)
    ).all()
    nodes = {}
    links = []
    for link, entity, section in rows:
        nodes[entity.id] = {
            "id": entity.id,
            "type": entity.entity_type,
            "name": entity.canonical_name,
            "external_ids": entity.external_ids,
            "metadata": entity.metadata_json,
        }
        links.append({
            "id": link.id,
            "entity_id": entity.id,
            "type": link.link_type,
            "section_id": link.section_id,
            "section": section.section_number if section else None,
            "confidence": link.confidence,
            "evidence": link.evidence,
            "source_url": link.source_url,
            "extraction_method": link.extraction_method,
            "metadata": link.metadata_json,
        })
    return {"bill_id": bill_id, "nodes": list(nodes.values()), "links": links}

def relationships_for_bill(db, bill_id: int):
    entity_ids = select(LegislativeEntityLink.entity_id).where(LegislativeEntityLink.bill_id == bill_id)
    rels = db.scalars(select(EntityRelationship).where(or_(
        EntityRelationship.source_entity_id.in_(entity_ids),
        EntityRelationship.target_entity_id.in_(entity_ids),
    ))).all()
    result=[]
    for r in rels:
        source=db.get(EvidenceEntity,r.source_entity_id)
        target=db.get(EvidenceEntity,r.target_entity_id)
        result.append({
            "id":r.id,
            "source_entity":{"id":source.id,"type":source.entity_type,"name":source.canonical_name},
            "target_entity":{"id":target.id,"type":target.entity_type,"name":target.canonical_name},
            "relation_type":r.relation_type,
            "evidence":r.evidence,
            "source_url":r.source_url,
            "observed_on":r.observed_on,
            "confidence":r.confidence,
            "source_system":r.source_system,
            "metadata":r.metadata_json,
        })
    return result


def create_relationship(db, source_entity_id: int, target_entity_id: int, relation_type: str,
                        evidence: str, source_url: str | None = None, observed_on: str | None = None,
                        confidence: float = 1.0, source_system: str = "manual", metadata=None):
    source = db.get(EvidenceEntity, source_entity_id)
    target = db.get(EvidenceEntity, target_entity_id)
    if not source or not target:
        raise ValueError("Source or target entity not found")
    existing = db.scalar(select(EntityRelationship).where(
        EntityRelationship.source_entity_id == source_entity_id,
        EntityRelationship.target_entity_id == target_entity_id,
        EntityRelationship.relation_type == relation_type,
        EntityRelationship.source_url == source_url,
    ))
    if existing:
        return existing
    relation = EntityRelationship(
        source_entity_id=source_entity_id,
        target_entity_id=target_entity_id,
        relation_type=relation_type,
        evidence=evidence,
        source_url=source_url,
        observed_on=observed_on,
        confidence=confidence,
        source_system=source_system,
        metadata_json=metadata or {},
    )
    db.add(relation)
    db.commit()
    db.refresh(relation)
    return relation
