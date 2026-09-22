from datetime import datetime
from sqlalchemy import select
from app.models.entities import (
    Bill, EvidenceEntity, LegislativeEntityLink, ResearchRun, ResearchStep,
)
from app.services.graph import sync_bill_graph
from app.services.external_evidence import import_fec_candidate, import_lda_client
from app.services.correlation import correlate_bill, correlations_for_bill

def _step(db, run_id, entity_id, source_system, action, status, reason, result=None):
    row=ResearchStep(
        run_id=run_id,
        entity_id=entity_id,
        source_system=source_system,
        action=action,
        status=status,
        reason=reason,
        result_json=result or {},
    )
    db.add(row)
    db.flush()
    return row

def run_bill_research(db, bill_id:int, filing_year:int|None=None,
                      max_lda_records_per_entity:int=50,
                      include_fec_candidate_links:bool=True,
                      include_lda_clients:bool=True):
    bill=db.get(Bill,bill_id)
    if not bill:
        raise ValueError("Bill not found")

    run=ResearchRun(bill_id=bill_id,status="running")
    db.add(run)
    db.flush()

    try:
        sync_bill_graph(db,bill_id)
        _step(db,run.id,None,"internal","sync_bill_graph","completed",
              "Refreshed deterministic bill entities before external research.")

        links=db.execute(
            select(LegislativeEntityLink,EvidenceEntity)
            .join(EvidenceEntity,LegislativeEntityLink.entity_id==EvidenceEntity.id)
            .where(LegislativeEntityLink.bill_id==bill_id)
        ).all()

        seen_entities={}
        for link,entity in links:
            if entity.id not in seen_entities:
                seen_entities[entity.id]={"entity":entity,"link_types":set()}
            seen_entities[entity.id]["link_types"].add(link.link_type)

        for entry in seen_entities.values():
            entity=entry["entity"]
            link_types=entry["link_types"]
            if entity.entity_type=="person":
                candidate_id=(entity.external_ids or {}).get("fec_candidate_id")
                if include_fec_candidate_links and candidate_id:
                    try:
                        result=import_fec_candidate(db,entity.id,candidate_id)
                        _step(db,run.id,entity.id,"fec","candidate_committees","completed",
                              "Bill-linked person has a verified FEC candidate identifier.",result)
                    except Exception as exc:
                        _step(db,run.id,entity.id,"fec","candidate_committees","failed",
                              "Verified FEC candidate identifier was present, but retrieval failed.",
                              {"error":str(exc)})
                elif include_fec_candidate_links:
                    _step(db,run.id,entity.id,"fec","candidate_committees","skipped",
                          "No verified FEC candidate identifier is attached to this bill-linked person.")
                else:
                    _step(db,run.id,entity.id,"fec","candidate_committees","skipped",
                          "FEC candidate research disabled for this run.")

            elif entity.entity_type=="organization" and "named_organization" in link_types:
                if include_lda_clients:
                    try:
                        result=import_lda_client(
                            db,
                            entity.canonical_name,
                            filing_year=filing_year,
                            max_records=max_lda_records_per_entity,
                            exact_client_match=True,
                        )
                        status="completed" if result.get("filing_count",0)>0 else "no_match"
                        reason=(
                            "Queried LDA.gov and retained only exact normalized client-name matches."
                            if status=="completed"
                            else "LDA.gov returned no exact normalized client-name matches."
                        )
                        _step(db,run.id,entity.id,"lda","client_filings",status,reason,result)
                    except Exception as exc:
                        _step(db,run.id,entity.id,"lda","client_filings","failed",
                              "Exact-name LDA client query failed.",{"error":str(exc)})
                else:
                    _step(db,run.id,entity.id,"lda","client_filings","skipped",
                          "LDA client research disabled for this run.")

        correlations=correlate_bill(db,bill_id)
        _step(db,run.id,None,"internal","correlate","completed",
              "Ran deterministic identifier/exact-name/alias correlation after evidence imports.",
              {"correlation_count":correlations.get("correlation_count",0)})

        steps=db.scalars(select(ResearchStep).where(ResearchStep.run_id==run.id)).all()
        counts={}
        for s in steps:
            counts[s.status]=counts.get(s.status,0)+1
        run.status="completed_with_errors" if counts.get("failed",0) else "completed"
        run.completed_at=datetime.utcnow()
        correlation_ids=[c["id"] for c in correlations.get("correlations",[])]
        run.summary_json={
            "step_counts":counts,
            "correlation_count":correlations.get("correlation_count",0),
            "correlation_ids":correlation_ids,
        }
        db.commit()
        return research_packet(db,run.id)
    except Exception as exc:
        run.status="failed"
        run.completed_at=datetime.utcnow()
        run.summary_json={"error":str(exc)}
        db.commit()
        raise

def research_packet(db, run_id:int):
    run=db.get(ResearchRun,run_id)
    if not run:
        raise ValueError("Research run not found")
    bill=db.get(Bill,run.bill_id)
    steps=db.scalars(
        select(ResearchStep).where(ResearchStep.run_id==run_id).order_by(ResearchStep.id)
    ).all()
    correlations=correlations_for_bill(db,run.bill_id)
    return {
        "run":{
            "id":run.id,
            "bill_id":run.bill_id,
            "status":run.status,
            "started_at":run.started_at.isoformat() if run.started_at else None,
            "completed_at":run.completed_at.isoformat() if run.completed_at else None,
            "summary":run.summary_json,
        },
        "bill":{
            "id":bill.id,
            "congress":bill.congress,
            "bill_type":bill.bill_type,
            "bill_number":bill.bill_number,
            "title":bill.title,
        },
        "steps":[{
            "id":s.id,
            "entity_id":s.entity_id,
            "source_system":s.source_system,
            "action":s.action,
            "status":s.status,
            "reason":s.reason,
            "result":s.result_json,
        } for s in steps],
        "correlations":correlations,
        "interpretation_note":"This packet records source-backed relationships and deterministic correlations. It does not establish influence, causation, conflicts of interest, or wrongdoing.",
    }
