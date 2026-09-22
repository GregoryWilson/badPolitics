from collections import Counter
from datetime import datetime
from sqlalchemy import select

from app.models.entities import (
    Bill, BillVersion, Section, ProvisionEvidencePacket, InvestigationQueueItem,
)
from app.services.evidence_packets import build_bill_packets

ACTIVE_STATUSES={"new","reviewing","needs_evidence"}

def _trigger_types(packet):
    triggers=set()
    for entry in packet.get("evidence",[]):
        kind=entry.get("kind")
        metadata=entry.get("metadata") or {}
        if kind=="scope_finding":
            triggers.add(metadata.get("category") or "scope_outlier")
        elif kind=="provision_lineage":
            event=metadata.get("event_type")
            if event in {"introduced","modified","removed","renumbered"}:
                triggers.add(f"lineage_{event}")
        elif kind=="candidate_amendment":
            triggers.add("candidate_amendment")
        elif kind in {"named_organization","potential_beneficiary_class","named_geography"}:
            triggers.add(kind)
        elif kind=="external_correlation":
            triggers.add("external_correlation")
        elif kind=="external_relationship":
            triggers.add("external_relationship")
        elif kind=="bill_level_fiscal_context":
            category=metadata.get("category")
            triggers.add(f"fiscal_{category}" if category else "fiscal_context")
        elif kind=="deterministic_finding":
            finding_kind=metadata.get("kind")
            triggers.add(f"bill_text_{finding_kind}" if finding_kind else "bill_text_signal")
    return sorted(triggers)

def _coverage(packet,narrative=None):
    entries=packet.get("evidence",[])
    kinds=Counter(entry.get("kind") for entry in entries)
    source_backed=sum(1 for entry in entries if entry.get("source_url"))
    return {
        "entry_count":len(entries),
        "source_backed_entry_count":source_backed,
        "has_section_text":kinds["section_text"]>0,
        "has_deterministic_findings":kinds["deterministic_finding"]>0,
        "has_scope_analysis":kinds["scope_finding"]>0,
        "has_lineage":kinds["provision_lineage"]>0,
        "has_candidate_amendment":kinds["candidate_amendment"]>0,
        "has_entity_context":sum(kinds[k] for k in ("named_organization","potential_beneficiary_class","named_geography"))>0,
        "has_external_context":kinds["external_correlation"]>0 or kinds["external_relationship"]>0,
        "has_fiscal_context":kinds["bill_level_fiscal_context"]>0,
        "has_local_synthesis":bool(narrative and not narrative.startswith("Narrative rejected")),
    }

def _gaps(packet):
    gaps=[]
    entries=packet.get("evidence",[])
    section_entries=[e for e in entries if e.get("kind")=="section_text"]
    if not section_entries or not section_entries[0].get("source_url"):
        gaps.append("section_source_url")

    for entry in entries:
        kind=entry.get("kind")
        if kind=="candidate_amendment" and not entry.get("source_url"):
            gaps.append("candidate_amendment_source_url")
        elif kind=="external_relationship" and not entry.get("source_url"):
            gaps.append("external_relationship_source_url")
        elif kind in {"named_organization","potential_beneficiary_class","named_geography"} and not entry.get("source_url"):
            gaps.append("section_entity_source_url")
        elif kind=="bill_level_fiscal_context" and not entry.get("source_url"):
            gaps.append("fiscal_context_source_url")
    return sorted(set(gaps))

def _bill_identity(bill):
    return {
        "id":bill.id,
        "jurisdiction":bill.jurisdiction,
        "session":(bill.metadata_json or {}).get("jurisdiction_session") or str(bill.congress),
        "congress":bill.congress,
        "bill_type":bill.bill_type,
        "bill_number":bill.bill_number,
        "title":bill.title,
        "latest_action":bill.latest_action,
    }

def _view(db,row):
    bill=db.get(Bill,row.bill_id)
    version=db.get(BillVersion,row.version_id)
    section=db.get(Section,row.section_id)
    packet=db.get(ProvisionEvidencePacket,row.packet_id)
    coverage=row.evidence_coverage or {}
    gaps=row.unresolved_gaps or []
    if row.status=="superseded":
        next_step="historical_record"
    elif row.status in {"completed","archived"}:
        next_step="none"
    elif gaps:
        next_step="resolve_evidence_gaps"
    else:
        next_step="review_packet"
    return {
        "id":row.id,
        "status":row.status,
        "trigger_types":row.trigger_types or [],
        "evidence_coverage":coverage,
        "unresolved_gaps":gaps,
        "suggested_next_step":next_step,
        "analyst_notes":row.analyst_notes,
        "created_at":row.created_at.isoformat() if row.created_at else None,
        "updated_at":row.updated_at.isoformat() if row.updated_at else None,
        "last_seen_at":row.last_seen_at.isoformat() if row.last_seen_at else None,
        "bill":_bill_identity(bill) if bill else None,
        "version":{
            "id":version.id,
            "code":version.version_code,
            "issued_on":version.issued_on,
            "source_url":version.source_url,
        } if version else None,
        "section":{
            "id":section.id,
            "number":section.section_number,
            "heading":section.heading,
        } if section else None,
        "packet":{
            "id":packet.id,
            "hash":packet.packet_hash,
            "narrative_status":(
                "rejected" if packet.narrative and packet.narrative.startswith("Narrative rejected")
                else ("complete" if packet.narrative else "not_generated")
            ),
        } if packet else None,
    }

def sync_bill_queue(db,bill_id:int,limit:int=50):
    bill=db.get(Bill,bill_id)
    if not bill:
        raise ValueError("Bill not found")
    packet_result=build_bill_packets(
        db,bill_id,generate_narrative=False,limit=max(1,min(limit,100))
    )
    now=datetime.utcnow()
    touched=[]
    current_keys=set()

    for packet_view in packet_result.get("packets",[]):
        packet=packet_view.get("packet") or {}
        packet_id=packet_view["packet_id"]
        packet_hash=packet_view["packet_hash"]
        version_id=packet_view["version_id"]
        section_id=packet_view["section_id"]
        current_keys.add((version_id,section_id,packet_hash))

        row=db.scalar(select(InvestigationQueueItem).where(
            InvestigationQueueItem.bill_id==bill_id,
            InvestigationQueueItem.version_id==version_id,
            InvestigationQueueItem.section_id==section_id,
            InvestigationQueueItem.packet_hash==packet_hash,
        ))
        triggers=_trigger_types(packet)
        coverage=_coverage(packet,packet_view.get("narrative"))
        gaps=_gaps(packet)
        if row:
            row.packet_id=packet_id
            row.trigger_types=triggers
            row.evidence_coverage=coverage
            row.unresolved_gaps=gaps
            row.last_seen_at=now
            row.updated_at=now
        else:
            row=InvestigationQueueItem(
                bill_id=bill_id,
                version_id=version_id,
                section_id=section_id,
                packet_id=packet_id,
                packet_hash=packet_hash,
                status="new",
                trigger_types=triggers,
                evidence_coverage=coverage,
                unresolved_gaps=gaps,
                created_at=now,
                updated_at=now,
                last_seen_at=now,
            )
            db.add(row)
        db.flush()
        touched.append(row.id)

        older=db.scalars(select(InvestigationQueueItem).where(
            InvestigationQueueItem.bill_id==bill_id,
            InvestigationQueueItem.version_id==version_id,
            InvestigationQueueItem.section_id==section_id,
            InvestigationQueueItem.packet_hash!=packet_hash,
            InvestigationQueueItem.status.in_(list(ACTIVE_STATUSES)),
        )).all()
        for old in older:
            old.status="superseded"
            old.updated_at=now

    db.commit()
    return {
        "bill_id":bill_id,
        "synced_count":len(touched),
        "queue_items":[_view(db,db.get(InvestigationQueueItem,item_id)) for item_id in touched],
        "interpretation_note":"Queue items organize evidence for human review. Trigger count, evidence coverage, workflow status, and queue position are not political scores or conclusions about a bill or political actor.",
    }

def list_queue(db,status:str|None=None,jurisdiction:str|None=None,bill_id:int|None=None,limit:int=100):
    query=select(InvestigationQueueItem)
    if status:
        query=query.where(InvestigationQueueItem.status==status)
    if bill_id is not None:
        query=query.where(InvestigationQueueItem.bill_id==bill_id)
    rows=db.scalars(
        query.order_by(InvestigationQueueItem.updated_at.desc(),InvestigationQueueItem.id.desc())
        .limit(max(1,min(limit,500)))
    ).all()
    if jurisdiction:
        jurisdiction=jurisdiction.upper()
        rows=[row for row in rows if (db.get(Bill,row.bill_id) and db.get(Bill,row.bill_id).jurisdiction==jurisdiction)]
    return [_view(db,row) for row in rows]

def queue_summary(db):
    rows=db.scalars(select(InvestigationQueueItem)).all()
    status_counts=Counter(row.status for row in rows)
    trigger_counts=Counter()
    gap_counts=Counter()
    for row in rows:
        trigger_counts.update(row.trigger_types or [])
        gap_counts.update(row.unresolved_gaps or [])
    return {
        "total":len(rows),
        "by_status":dict(sorted(status_counts.items())),
        "by_trigger":dict(sorted(trigger_counts.items())),
        "evidence_gaps":dict(sorted(gap_counts.items())),
        "interpretation_note":"This summary describes workflow volume and evidence coverage only; it is not a ranking of legislation or political actors.",
    }

def update_queue_item(db,item_id:int,status:str|None=None,analyst_notes:str|None=None):
    row=db.get(InvestigationQueueItem,item_id)
    if not row:
        raise ValueError("Queue item not found")
    if row.status=="superseded" and status is not None:
        raise ValueError("Superseded queue items are historical and cannot be reopened")
    if status is not None:
        row.status=status
    if analyst_notes is not None:
        row.analyst_notes=analyst_notes
    row.updated_at=datetime.utcnow()
    db.commit(); db.refresh(row)
    return _view(db,row)
