import hashlib
import json
import re
from sqlalchemy import select

from app.core.config import settings
from app.models.entities import (
    Bill, BillVersion, Section, Finding, ScopeFinding, ProvisionLineage,
    AmendmentAttribution, Amendment, LegislativeEntityLink, EvidenceEntity,
    CorrelationFinding, EntityRelationship, ComparativeFinding, LegislativeDocument,
    ProvisionEvidencePacket,
)
from app.services.lineage import build_lineage
from app.services.scope_analysis import run_scope_analysis
from app.services.fiscal_analysis import run_fiscal_analysis
from app.services.llm import synthesize_evidence_packet

CITATION_RE=re.compile(r"\[([A-Z]+\d+)\]")

def _latest_version(db,bill_id):
    return db.scalar(
        select(BillVersion)
        .where(BillVersion.bill_id==bill_id)
        .order_by(BillVersion.issued_on.desc(),BillVersion.id.desc())
    )

def _source_url_for_version(version):
    return version.source_url if version else None

def _append(entries,prefix,counter,kind,summary,evidence,source_url=None,metadata=None):
    evidence_id=f"{prefix}{counter[prefix]}"
    counter[prefix]+=1
    entries.append({
        "evidence_id":evidence_id,
        "kind":kind,
        "summary":summary,
        "evidence":evidence,
        "source_url":source_url,
        "metadata":metadata or {},
    })
    return evidence_id

def noteworthy_section_ids(db,bill_id,version_id):
    ids=set(db.scalars(
        select(Finding.section_id).where(
            Finding.version_id==version_id,
            Finding.section_id.is_not(None),
        )
    ).all())
    ids.update(db.scalars(
        select(ScopeFinding.section_id).where(
            ScopeFinding.bill_id==bill_id,
            ScopeFinding.version_id==version_id,
        )
    ).all())
    version_sections=db.scalars(
        select(Section).where(Section.version_id==version_id)
    ).all()
    by_number={s.section_number:s.id for s in version_sections}
    for row in db.scalars(
        select(ProvisionLineage).where(
            ProvisionLineage.bill_id==bill_id,
            ProvisionLineage.to_version_id==version_id,
            ProvisionLineage.from_version_id.is_not(None),
            ProvisionLineage.event_type.in_(["introduced","modified"]),
        )
    ).all():
        if row.section_number in by_number:
            ids.add(by_number[row.section_number])
    ids.update(db.scalars(
        select(LegislativeEntityLink.section_id).where(
            LegislativeEntityLink.bill_id==bill_id,
            LegislativeEntityLink.section_id.is_not(None),
        )
    ).all())
    return {i for i in ids if i}

def _section_entity_context(db,bill_id,section_id,entries,counter):
    links=db.scalars(
        select(LegislativeEntityLink).where(
            LegislativeEntityLink.bill_id==bill_id,
            LegislativeEntityLink.section_id==section_id,
        )
    ).all()
    entity_ids=set()
    for link in links:
        entity=db.get(EvidenceEntity,link.entity_id)
        if not entity:
            continue
        entity_ids.add(entity.id)
        _append(
            entries,"E",counter,link.link_type,
            f"{entity.canonical_name} is linked to this section as {link.link_type.replace('_',' ')}.",
            link.evidence,
            link.source_url,
            {
                "entity_id":entity.id,
                "entity_type":entity.entity_type,
                "confidence":link.confidence,
                "extraction_method":link.extraction_method,
            },
        )

    if not entity_ids:
        return
    correlations=db.scalars(
        select(CorrelationFinding).where(
            CorrelationFinding.bill_id==bill_id,
            CorrelationFinding.legislative_entity_id.in_(entity_ids),
        )
    ).all()
    for corr in correlations:
        left=db.get(EvidenceEntity,corr.legislative_entity_id)
        right=db.get(EvidenceEntity,corr.matched_entity_id)
        if not left or not right:
            continue
        relationship_ids=(corr.metadata_json or {}).get("relationship_ids") or []
        _append(
            entries,"C",counter,"external_correlation",
            f"{left.canonical_name} correlates with external evidence for {right.canonical_name}.",
            corr.evidence,
            None,
            {
                "correlation_id":corr.id,
                "match_basis":corr.match_basis,
                "confidence":corr.confidence,
                "legislative_entity_id":left.id,
                "matched_entity_id":right.id,
            },
        )
        rel_query=select(EntityRelationship).where(
            (
                (EntityRelationship.source_entity_id==right.id)
                | (EntityRelationship.target_entity_id==right.id)
            )
        )
        if relationship_ids:
            rel_query=rel_query.where(EntityRelationship.id.in_(relationship_ids))
        for rel in db.scalars(rel_query).all():
            _append(
                entries,"X",counter,"external_relationship",
                f"External source records relationship type {rel.relation_type}.",
                rel.evidence,
                rel.source_url,
                {
                    "relationship_id":rel.id,
                    "source_system":rel.source_system,
                    "observed_on":rel.observed_on,
                    "source_entity_id":rel.source_entity_id,
                    "target_entity_id":rel.target_entity_id,
                },
            )

def _lineage_context(db,bill_id,version,section,entries,counter):
    events=db.scalars(
        select(ProvisionLineage).where(
            ProvisionLineage.bill_id==bill_id,
            ProvisionLineage.section_number==section.section_number,
            ProvisionLineage.to_version_id==version.id,
        )
    ).all()
    for event in events:
        lid=_append(
            entries,"L",counter,"provision_lineage",
            f"Section {section.section_number} was {event.event_type} in version {version.version_code}.",
            event.diff_text or event.new_text or event.old_text or "",
            version.source_url,
            {
                "lineage_id":event.id,
                "event_type":event.event_type,
                "from_version_id":event.from_version_id,
                "to_version_id":event.to_version_id,
                "similarity":event.similarity,
            },
        )
        attrs=db.scalars(
            select(AmendmentAttribution).where(
                AmendmentAttribution.lineage_id==event.id
            ).order_by(AmendmentAttribution.confidence.desc())
        ).all()
        for attr in attrs:
            amendment=db.get(Amendment,attr.amendment_id)
            if not amendment:
                continue
            _append(
                entries,"A",counter,"candidate_amendment",
                f"Candidate amendment association: {amendment.amendment_type.upper()} {amendment.amendment_number}.",
                attr.evidence,
                amendment.source_url,
                {
                    "lineage_evidence_id":lid,
                    "amendment_id":amendment.id,
                    "attribution_type":attr.attribution_type,
                    "confidence":attr.confidence,
                    "description":amendment.description,
                    "latest_action":amendment.latest_action,
                    "attribution_metadata":attr.metadata_json,
                },
            )

def _bill_level_fiscal_context(db,bill_id,entries,counter):
    docs={d.id:d for d in db.scalars(
        select(LegislativeDocument).where(LegislativeDocument.bill_id==bill_id)
    ).all()}
    for finding in db.scalars(
        select(ComparativeFinding)
        .where(ComparativeFinding.bill_id==bill_id)
        .order_by(ComparativeFinding.confidence.desc(),ComparativeFinding.id)
        .limit(20)
    ).all():
        doc=docs.get(finding.document_id)
        _append(
            entries,"F",counter,"bill_level_fiscal_context",
            finding.statement,
            finding.evidence,
            doc.source_url if doc else None,
            {
                "comparative_finding_id":finding.id,
                "category":finding.category,
                "confidence":finding.confidence,
                "source_kind":finding.source_kind,
                "document_id":finding.document_id,
                "scope":"bill_level_context_not_attributed_to_section",
            },
        )

def build_section_packet(db,bill_id:int,section_id:int,generate_narrative:bool=False):
    bill=db.get(Bill,bill_id)
    if not bill:
        raise ValueError("Bill not found")
    version=_latest_version(db,bill_id)
    if not version:
        raise ValueError("Bill has no stored text version")
    section=db.get(Section,section_id)
    if not section or section.version_id!=version.id:
        raise ValueError("Section not found in latest bill version")

    build_lineage(db,bill_id)
    run_fiscal_analysis(db,bill_id)
    run_scope_analysis(db,bill_id)

    entries=[]
    counter={key:1 for key in ("S","D","Q","L","A","E","C","X","F")}
    _append(
        entries,"S",counter,"section_text",
        f"Latest text for section {section.section_number}.",
        section.text,
        version.source_url,
        {
            "section_id":section.id,
            "section_number":section.section_number,
            "heading":section.heading,
            "version_id":version.id,
            "version_code":version.version_code,
            "version_sha256":version.sha256,
        },
    )

    for finding in db.scalars(
        select(Finding).where(
            Finding.version_id==version.id,
            Finding.section_id==section.id,
        ).order_by(Finding.severity.desc(),Finding.id)
    ).all():
        _append(
            entries,"D",counter,"deterministic_finding",
            finding.label,
            finding.evidence,
            version.source_url,
            {
                "finding_id":finding.id,
                "kind":finding.kind,
                "severity":finding.severity,
            },
        )

    for finding in db.scalars(
        select(ScopeFinding).where(
            ScopeFinding.bill_id==bill_id,
            ScopeFinding.version_id==version.id,
            ScopeFinding.section_id==section.id,
        )
    ).all():
        _append(
            entries,"Q",counter,"scope_finding",
            finding.statement,
            finding.evidence,
            version.source_url,
            {
                "scope_finding_id":finding.id,
                "category":finding.category,
                "confidence":finding.confidence,
                "anchor_similarity":finding.anchor_similarity,
                "peer_similarity":finding.peer_similarity,
                **(finding.metadata_json or {}),
            },
        )

    _lineage_context(db,bill_id,version,section,entries,counter)
    _section_entity_context(db,bill_id,section.id,entries,counter)
    _bill_level_fiscal_context(db,bill_id,entries,counter)

    packet={
        "schema_version":"1.0",
        "bill":{
            "id":bill.id,
            "jurisdiction":bill.jurisdiction,
            "session":(bill.metadata_json or {}).get("jurisdiction_session") or str(bill.congress),
            "bill_type":bill.bill_type,
            "bill_number":bill.bill_number,
            "title":bill.title,
        },
        "version":{
            "id":version.id,
            "code":version.version_code,
            "issued_on":version.issued_on,
            "source_url":version.source_url,
            "sha256":version.sha256,
        },
        "section":{
            "id":section.id,
            "number":section.section_number,
            "heading":section.heading,
        },
        "evidence":entries,
        "interpretation_note":"The packet combines source-backed records and deterministic review signals. Correlations and amendment associations do not establish influence, motive, causation, conflict of interest, wrongdoing, or authorship.",
    }
    canonical=json.dumps(packet,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    packet_hash=hashlib.sha256(canonical.encode()).hexdigest()
    existing=db.scalar(select(ProvisionEvidencePacket).where(
        ProvisionEvidencePacket.bill_id==bill_id,
        ProvisionEvidencePacket.version_id==version.id,
        ProvisionEvidencePacket.section_id==section.id,
        ProvisionEvidencePacket.packet_hash==packet_hash,
    ))
    if existing:
        row=existing
    else:
        row=ProvisionEvidencePacket(
            bill_id=bill_id,
            version_id=version.id,
            section_id=section.id,
            packet_hash=packet_hash,
            packet_json=packet,
        )
        db.add(row); db.flush()

    if generate_narrative:
        narrative=synthesize_evidence_packet(packet)
        valid_ids={entry["evidence_id"] for entry in entries}
        used_ids=set(CITATION_RE.findall(narrative or ""))
        invalid=sorted(used_ids-valid_ids)
        if invalid:
            row.narrative=(
                "Narrative rejected because it cited evidence IDs not present in the packet: "
                +", ".join(invalid)
            )
        else:
            row.narrative=narrative
        row.llm_model=settings.llm_model
    db.commit(); db.refresh(row)
    return packet_view(row)

def build_bill_packets(db,bill_id:int,generate_narrative:bool=False,limit:int=25):
    bill=db.get(Bill,bill_id)
    if not bill:
        raise ValueError("Bill not found")
    version=_latest_version(db,bill_id)
    if not version:
        raise ValueError("Bill has no stored text version")
    build_lineage(db,bill_id)
    run_fiscal_analysis(db,bill_id)
    run_scope_analysis(db,bill_id)
    section_ids=sorted(noteworthy_section_ids(db,bill_id,version.id))[:max(1,min(limit,100))]
    packets=[
        build_section_packet(db,bill_id,section_id,generate_narrative=generate_narrative)
        for section_id in section_ids
    ]
    return {
        "bill_id":bill_id,
        "version_id":version.id,
        "packet_count":len(packets),
        "packets":packets,
        "interpretation_note":"Packets are evidence bundles for review. Their existence is not an evaluative judgment about the legislation or any political actor.",
    }

def packet_view(row):
    return {
        "packet_id":row.id,
        "bill_id":row.bill_id,
        "version_id":row.version_id,
        "section_id":row.section_id,
        "packet_hash":row.packet_hash,
        "packet":row.packet_json,
        "narrative":row.narrative,
        "llm_model":row.llm_model,
        "created_at":row.created_at.isoformat() if row.created_at else None,
    }

def get_packet(db,packet_id:int):
    row=db.get(ProvisionEvidencePacket,packet_id)
    if not row:
        raise ValueError("Evidence packet not found")
    return packet_view(row)

def list_packets(db,bill_id:int):
    rows=db.scalars(
        select(ProvisionEvidencePacket)
        .where(ProvisionEvidencePacket.bill_id==bill_id)
        .order_by(ProvisionEvidencePacket.id.desc())
    ).all()
    latest_by_section={}
    for row in rows:
        latest_by_section.setdefault(row.section_id,row)
    return [packet_view(row) for row in latest_by_section.values()]
