from fastapi import FastAPI,Depends,HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pathlib import Path
import asyncio
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db.base import Base
from app.db.session import engine,get_db,SessionLocal
from app.models.entities import Bill,BillVersion,Section,Finding,BillAction,BillSponsor,Amendment,EvidenceEntity,ExternalEvidenceRecord,WatchRule,LegislativeDocument
from app.services.ingest import ingest_federal,ingest_jurisdiction,discover_jurisdiction
from app.services.monitor import poll_recent_bills
from app.services.diffing import summary,unified
from app.services.llm import deep_dive
from app.services.graph import sync_bill_graph,graph_for_bill,relationships_for_bill,create_relationship,get_or_create_entity
from app.schemas.graph import EntityCreate,RelationshipCreate
from app.services.metrics import bill_metrics
from app.schemas.evidence import FECCandidateImport,FECReceiptImport,LDAClientImport
from app.services.external_evidence import import_fec_candidate,import_fec_receipts,import_lda_client
from app.services.correlation import correlate_bill,correlations_for_bill
from app.schemas.research import ResearchRunRequest
from app.services.research import run_bill_research,research_packet
from app.services.reporting import build_report,get_report
from app.services.fiscal_analysis import run_fiscal_analysis,fiscal_analysis_result
from app.services.lineage import build_lineage,lineage_result
from app.services.scope_analysis import run_scope_analysis,scope_analysis_result
from app.services.evidence_packets import build_bill_packets,build_section_packet,get_packet,list_packets
from app.schemas.watch import WatchCreate,WatchUpdate
from app.services.watch import run_watch,run_active_watches,list_events,get_scan
from app.core.config import settings
from app.jurisdictions import list_adapters

Base.metadata.create_all(engine)
app=FastAPI(title="LegisWatch",version="1.6.0")
STATIC_DIR=Path(__file__).resolve().parent/"static"
app.mount("/static",StaticFiles(directory=str(STATIC_DIR)),name="static")

@app.get("/",include_in_schema=False)
def dashboard():
    return RedirectResponse(url="/static/index.html")

@app.get("/health")
def health(): return {"ok":True,"version":"1.6.0","watch_poll_minutes":settings.watch_poll_minutes}

@app.post("/ingest/federal/{congress}/{bill_type}/{number}")
def ingest(congress:int,bill_type:str,number:str,db:Session=Depends(get_db)):
    try: return ingest_federal(db,congress,bill_type,number)
    except Exception as e: raise HTTPException(502,str(e))

@app.get("/jurisdictions")
def jurisdictions():
    return list_adapters()

@app.post("/jurisdictions/{jurisdiction}/ingest/{session}/{bill_type}/{number}")
def jurisdiction_ingest(jurisdiction:str,session:str,bill_type:str,number:str,db:Session=Depends(get_db)):
    try:
        return ingest_jurisdiction(db,jurisdiction,session,bill_type,number)
    except ValueError as e:
        raise HTTPException(404,str(e))
    except Exception as e:
        raise HTTPException(502,str(e))

@app.post("/jurisdictions/{jurisdiction}/discover/{session}")
def jurisdiction_discover(jurisdiction:str,session:str,limit:int=100,ingest:bool=False,db:Session=Depends(get_db)):
    try:
        return discover_jurisdiction(db,jurisdiction,session,limit,ingest)
    except ValueError as e:
        raise HTTPException(404,str(e))
    except Exception as e:
        raise HTTPException(502,str(e))

@app.post("/monitor/federal/{congress}")
def monitor(congress:int,limit:int=50,db:Session=Depends(get_db)):
    try: return {"results":poll_recent_bills(db,congress,limit)}
    except Exception as e: raise HTTPException(502,str(e))

@app.get("/bills")
def bills(db:Session=Depends(get_db)):
    rows=db.scalars(select(Bill).order_by(Bill.id.desc())).all()
    return [{
        "id":b.id,
        "jurisdiction":b.jurisdiction,
        "session":(b.metadata_json or {}).get("jurisdiction_session") or str(b.congress),
        "congress":b.congress,
        "bill_type":b.bill_type,
        "bill_number":b.bill_number,
        "title":b.title,
        "latest_action":b.latest_action,
    } for b in rows]

@app.get("/bills/{bill_id}/documents")
def bill_documents(bill_id:int,db:Session=Depends(get_db)):
    if not db.get(Bill,bill_id):
        raise HTTPException(404,"Bill not found")
    rows=db.scalars(
        select(LegislativeDocument)
        .where(LegislativeDocument.bill_id==bill_id)
        .order_by(LegislativeDocument.document_type,LegislativeDocument.id)
    ).all()
    return [{
        "id":d.id,
        "document_type":d.document_type,
        "description":d.description,
        "source_url":d.source_url,
        "source_system":d.source_system,
        "issued_on":d.issued_on,
        "format":d.format,
        "sha256":d.sha256,
        "has_text":d.text is not None,
        "metadata":d.metadata_json,
    } for d in rows]

@app.get("/bills/{bill_id}/timeline")
def timeline(bill_id:int,db:Session=Depends(get_db)):
    actions=db.scalars(select(BillAction).where(BillAction.bill_id==bill_id).order_by(BillAction.action_date.desc())).all()
    sponsors=db.scalars(select(BillSponsor).where(BillSponsor.bill_id==bill_id).order_by(BillSponsor.role,BillSponsor.full_name)).all()
    amendments=db.scalars(select(Amendment).where(Amendment.bill_id==bill_id).order_by(Amendment.id.desc())).all()
    return {"actions":[{"date":a.action_date,"text":a.text,"code":a.action_code} for a in actions],"sponsors":[{"name":s.full_name,"role":s.role,"party":s.party,"state":s.state,"district":s.district,"bioguide_id":s.bioguide_id} for s in sponsors],"amendments":[{"type":a.amendment_type,"number":a.amendment_number,"description":a.description,"latest_action":a.latest_action,"source_url":a.source_url} for a in amendments]}

@app.get("/bills/{bill_id}/findings")
def findings(bill_id:int,db:Session=Depends(get_db)):
    rows=db.execute(select(Finding,Section,BillVersion).join(Section,Finding.section_id==Section.id).join(BillVersion,Finding.version_id==BillVersion.id).where(BillVersion.bill_id==bill_id).order_by(Finding.severity.desc())).all()
    return [{"finding_id":f.id,"version":v.version_code,"section":s.section_number,"heading":s.heading,"kind":f.kind,"severity":f.severity,"label":f.label,"evidence":f.evidence,"metadata":f.metadata_json} for f,s,v in rows]

@app.get("/bills/{bill_id}/diff/latest")
def diff_latest(bill_id:int,db:Session=Depends(get_db)):
    versions=db.scalars(select(BillVersion).where(BillVersion.bill_id==bill_id).order_by(BillVersion.issued_on.desc(),BillVersion.id.desc())).all()
    if len(versions)<2: raise HTTPException(404,"Need at least two versions")
    new,old=versions[0],versions[1]
    return {"old":old.version_code,"new":new.version_code,"summary":summary(old.text,new.text),"diff":unified(old.text,new.text,old.version_code,new.version_code)[:200000]}

@app.post("/sections/{section_id}/deep-dive")
def section_deep_dive(section_id:int,db:Session=Depends(get_db)):
    sec=db.get(Section,section_id)
    if not sec: raise HTTPException(404,"Section not found")
    version=db.get(BillVersion,sec.version_id); bill=db.get(Bill,version.bill_id)
    fs=db.scalars(select(Finding).where(Finding.section_id==section_id).order_by(Finding.severity.desc())).all()
    try: analysis=deep_dive(bill.title or f"{bill.bill_type} {bill.bill_number}",sec.text,[{"kind":f.kind,"evidence":f.evidence} for f in fs])
    except Exception as e: raise HTTPException(502,f"Local LLM failed: {e}")
    return {"bill":bill.title,"version":version.version_code,"section":sec.section_number,"analysis":analysis}


@app.post("/bills/{bill_id}/graph/sync")
def graph_sync(bill_id:int,db:Session=Depends(get_db)):
    try: return sync_bill_graph(db,bill_id)
    except ValueError as e: raise HTTPException(404,str(e))

@app.get("/bills/{bill_id}/graph")
def graph_get(bill_id:int,depth:int=2,db:Session=Depends(get_db)):
    if not db.get(Bill,bill_id): raise HTTPException(404,"Bill not found")
    graph=graph_for_bill(db,bill_id)
    graph["relationships"]=relationships_for_bill(db,bill_id,depth)
    return graph

@app.post("/graph/relationships")
def relationship_create(payload:RelationshipCreate,db:Session=Depends(get_db)):
    try:
        r=create_relationship(
            db,
            payload.source_entity_id,
            payload.target_entity_id,
            payload.relation_type,
            payload.evidence,
            payload.source_url,
            payload.observed_on,
            payload.confidence,
            payload.source_system,
            payload.metadata,
        )
    except ValueError as e:
        raise HTTPException(404,str(e))
    return {
        "id":r.id,
        "source_entity_id":r.source_entity_id,
        "target_entity_id":r.target_entity_id,
        "relation_type":r.relation_type,
        "evidence":r.evidence,
        "source_url":r.source_url,
        "observed_on":r.observed_on,
        "confidence":r.confidence,
        "source_system":r.source_system,
        "metadata":r.metadata_json,
    }


@app.post("/graph/entities")
def entity_create(payload:EntityCreate,db:Session=Depends(get_db)):
    entity=get_or_create_entity(
        db,
        payload.entity_type,
        payload.canonical_name,
        payload.external_ids,
        payload.metadata,
    )
    db.commit()
    db.refresh(entity)
    return {
        "id":entity.id,
        "type":entity.entity_type,
        "name":entity.canonical_name,
        "external_ids":entity.external_ids,
        "metadata":entity.metadata_json,
    }

@app.get("/graph/entities/{entity_id}")
def entity_get(entity_id:int,db:Session=Depends(get_db)):
    entity=db.get(EvidenceEntity,entity_id)
    if not entity: raise HTTPException(404,"Entity not found")
    return {
        "id":entity.id,
        "type":entity.entity_type,
        "name":entity.canonical_name,
        "external_ids":entity.external_ids,
        "metadata":entity.metadata_json,
    }


@app.get("/bills/{bill_id}/metrics")
def metrics_get(bill_id:int,db:Session=Depends(get_db)):
    try:
        return bill_metrics(db,bill_id)
    except ValueError as e:
        raise HTTPException(404,str(e))


@app.post("/evidence/fec/candidate")
def evidence_fec_candidate(payload:FECCandidateImport,db:Session=Depends(get_db)):
    try:
        return import_fec_candidate(db,payload.person_entity_id,payload.candidate_id,payload.cycle)
    except ValueError as e:
        raise HTTPException(404,str(e))
    except Exception as e:
        raise HTTPException(502,f"FEC import failed: {e}")

@app.post("/evidence/fec/receipts")
def evidence_fec_receipts(payload:FECReceiptImport,db:Session=Depends(get_db)):
    try:
        return import_fec_receipts(db,payload.committee_entity_id,payload.committee_id,payload.contributor_name,payload.min_date,payload.max_date)
    except ValueError as e:
        raise HTTPException(404,str(e))
    except Exception as e:
        raise HTTPException(502,f"FEC receipt import failed: {e}")

@app.post("/evidence/lda/client")
def evidence_lda_client(payload:LDAClientImport,db:Session=Depends(get_db)):
    try:
        return import_lda_client(db,payload.client_name,payload.filing_year,payload.max_records)
    except Exception as e:
        raise HTTPException(502,f"LDA import failed: {e}")

@app.get("/evidence/records")
def evidence_records(source_system:str|None=None,record_type:str|None=None,limit:int=100,db:Session=Depends(get_db)):
    q=select(ExternalEvidenceRecord).order_by(ExternalEvidenceRecord.id.desc()).limit(max(1,min(limit,500)))
    if source_system:
        q=q.where(ExternalEvidenceRecord.source_system==source_system)
    if record_type:
        q=q.where(ExternalEvidenceRecord.record_type==record_type)
    rows=db.scalars(q).all()
    return [{
        "id":r.id,
        "source_system":r.source_system,
        "record_type":r.record_type,
        "external_id":r.external_id,
        "observed_on":r.observed_on,
        "source_url":r.source_url,
        "raw":r.raw_json,
    } for r in rows]


@app.post("/bills/{bill_id}/correlate")
def bill_correlate(bill_id:int,db:Session=Depends(get_db)):
    try:
        return correlate_bill(db,bill_id)
    except ValueError as e:
        raise HTTPException(404,str(e))

@app.get("/bills/{bill_id}/correlations")
def bill_correlations(bill_id:int,db:Session=Depends(get_db)):
    if not db.get(Bill,bill_id):
        raise HTTPException(404,"Bill not found")
    return correlations_for_bill(db,bill_id)


@app.post("/bills/{bill_id}/research")
def bill_research(bill_id:int,payload:ResearchRunRequest,db:Session=Depends(get_db)):
    try:
        return run_bill_research(
            db,
            bill_id,
            filing_year=payload.filing_year,
            max_lda_records_per_entity=payload.max_lda_records_per_entity,
            include_fec_candidate_links=payload.include_fec_candidate_links,
            include_lda_clients=payload.include_lda_clients,
        )
    except ValueError as e:
        raise HTTPException(404,str(e))
    except Exception as e:
        raise HTTPException(502,f"Research orchestration failed: {e}")

@app.get("/research/{run_id}")
def research_get(run_id:int,db:Session=Depends(get_db)):
    try:
        return research_packet(db,run_id)
    except ValueError as e:
        raise HTTPException(404,str(e))


@app.post("/bills/{bill_id}/fiscal-analysis")
def fiscal_analyze(bill_id:int,db:Session=Depends(get_db)):
    try:
        return run_fiscal_analysis(db,bill_id)
    except ValueError as e:
        raise HTTPException(404,str(e))

@app.get("/bills/{bill_id}/fiscal-analysis")
def fiscal_get(bill_id:int,db:Session=Depends(get_db)):
    try:
        return fiscal_analysis_result(db,bill_id)
    except ValueError as e:
        raise HTTPException(404,str(e))

@app.post("/bills/{bill_id}/lineage")
def lineage_build(bill_id:int,db:Session=Depends(get_db)):
    try:
        return build_lineage(db,bill_id)
    except ValueError as e:
        raise HTTPException(404,str(e))

@app.get("/bills/{bill_id}/lineage")
def lineage_get(bill_id:int,db:Session=Depends(get_db)):
    try:
        return lineage_result(db,bill_id)
    except ValueError as e:
        raise HTTPException(404,str(e))

@app.post("/bills/{bill_id}/scope-analysis")
def scope_analyze(bill_id:int,db:Session=Depends(get_db)):
    try:
        build_lineage(db,bill_id)
        return run_scope_analysis(db,bill_id)
    except ValueError as e:
        raise HTTPException(404,str(e))

@app.get("/bills/{bill_id}/scope-analysis")
def scope_get(bill_id:int,db:Session=Depends(get_db)):
    try:
        return scope_analysis_result(db,bill_id)
    except ValueError as e:
        raise HTTPException(404,str(e))

@app.post("/bills/{bill_id}/evidence-packets")
def evidence_packets_build(
    bill_id:int,
    generate_narrative:bool=False,
    limit:int=25,
    db:Session=Depends(get_db),
):
    try:
        return build_bill_packets(db,bill_id,generate_narrative=generate_narrative,limit=limit)
    except ValueError as e:
        raise HTTPException(404,str(e))
    except Exception as e:
        raise HTTPException(502,f"Evidence packet build failed: {e}")

@app.get("/bills/{bill_id}/evidence-packets")
def evidence_packets_list(bill_id:int,db:Session=Depends(get_db)):
    if not db.get(Bill,bill_id):
        raise HTTPException(404,"Bill not found")
    return list_packets(db,bill_id)

@app.post("/sections/{section_id}/evidence-packet")
def section_evidence_packet(
    section_id:int,
    generate_narrative:bool=False,
    db:Session=Depends(get_db),
):
    section=db.get(Section,section_id)
    if not section:
        raise HTTPException(404,"Section not found")
    version=db.get(BillVersion,section.version_id)
    if not version:
        raise HTTPException(404,"Bill version not found")
    try:
        return build_section_packet(
            db,version.bill_id,section_id,generate_narrative=generate_narrative
        )
    except ValueError as e:
        raise HTTPException(404,str(e))
    except Exception as e:
        raise HTTPException(502,f"Evidence packet build failed: {e}")

@app.get("/evidence-packets/{packet_id}")
def evidence_packet_get(packet_id:int,db:Session=Depends(get_db)):
    try:
        return get_packet(db,packet_id)
    except ValueError as e:
        raise HTTPException(404,str(e))

@app.post("/bills/{bill_id}/reports")
def report_create(bill_id:int,research_run_id:int|None=None,db:Session=Depends(get_db)):
    try:
        return build_report(db,bill_id,research_run_id)
    except ValueError as e:
        raise HTTPException(404,str(e))

@app.get("/reports/{report_id}")
def report_get(report_id:int,db:Session=Depends(get_db)):
    try:
        return get_report(db,report_id)
    except ValueError as e:
        raise HTTPException(404,str(e))


_watch_task=None

async def _watch_loop():
    interval=max(1,int(settings.watch_poll_minutes))*60
    while True:
        try:
            await asyncio.to_thread(_run_all_watches_background)
        except Exception:
            pass
        await asyncio.sleep(interval)

def _run_all_watches_background():
    db=SessionLocal()
    try:
        return run_active_watches(db)
    finally:
        db.close()

@app.on_event("startup")
async def start_watch_loop():
    global _watch_task
    if settings.watch_poll_minutes>0 and _watch_task is None:
        _watch_task=asyncio.create_task(_watch_loop())

@app.on_event("shutdown")
async def stop_watch_loop():
    global _watch_task
    if _watch_task:
        _watch_task.cancel()
        try:
            await _watch_task
        except asyncio.CancelledError:
            pass
        _watch_task=None

@app.post("/watches")
def watch_create(payload:WatchCreate,db:Session=Depends(get_db)):
    bill_type=payload.bill_type.lower() if payload.bill_type else None
    bill_number=str(payload.bill_number) if payload.bill_number else None
    candidates=db.scalars(select(WatchRule).where(
        WatchRule.target_type==payload.target_type,
        WatchRule.jurisdiction==payload.jurisdiction,
        WatchRule.congress==payload.congress,
        WatchRule.bill_type==bill_type,
        WatchRule.bill_number==bill_number,
    )).all()
    existing=next((
        w for w in candidates
        if payload.target_type!="session"
        or (w.metadata_json or {}).get("session")==payload.metadata.get("session")
    ),None)
    if existing:
        existing.active=True
        existing.auto_research=payload.auto_research
        existing.auto_report=payload.auto_report
        existing.metadata_json=payload.metadata
        db.commit(); db.refresh(existing)
        return _watch_view(existing)
    watch=WatchRule(
        name=payload.name,
        target_type=payload.target_type,
        jurisdiction=payload.jurisdiction,
        congress=payload.congress,
        bill_type=bill_type,
        bill_number=bill_number,
        auto_research=payload.auto_research,
        auto_report=payload.auto_report,
        metadata_json={
            **payload.metadata,
            **({"session":payload.metadata.get("session")} if payload.metadata.get("session") else {}),
        },
    )
    db.add(watch); db.commit(); db.refresh(watch)
    return _watch_view(watch)

@app.get("/watches")
def watch_list(active_only:bool=False,db:Session=Depends(get_db)):
    q=select(WatchRule).order_by(WatchRule.id)
    if active_only:
        q=q.where(WatchRule.active==True)
    return [_watch_view(w) for w in db.scalars(q).all()]

@app.patch("/watches/{watch_id}")
def watch_update(watch_id:int,payload:WatchUpdate,db:Session=Depends(get_db)):
    watch=db.get(WatchRule,watch_id)
    if not watch: raise HTTPException(404,"Watch rule not found")
    for field in ("active","auto_research","auto_report"):
        value=getattr(payload,field)
        if value is not None: setattr(watch,field,value)
    db.commit(); db.refresh(watch)
    return _watch_view(watch)

@app.post("/watches/{watch_id}/scan")
def watch_scan(watch_id:int,db:Session=Depends(get_db)):
    try: return run_watch(db,watch_id)
    except ValueError as e: raise HTTPException(404,str(e))
    except Exception as e: raise HTTPException(502,f"Watch scan failed: {e}")

@app.post("/watches/run-all")
def watch_scan_all(db:Session=Depends(get_db)):
    return {"results":run_active_watches(db)}

@app.get("/watch-scans/{scan_id}")
def watch_scan_get(scan_id:int,db:Session=Depends(get_db)):
    try: return get_scan(db,scan_id)
    except ValueError as e: raise HTTPException(404,str(e))

@app.get("/watch-events")
def watch_events(watch_rule_id:int|None=None,limit:int=100,db:Session=Depends(get_db)):
    return list_events(db,watch_rule_id,limit)

def _watch_view(watch):
    return {
        "id":watch.id,"name":watch.name,"target_type":watch.target_type,
        "jurisdiction":watch.jurisdiction,"congress":watch.congress,
        "bill_type":watch.bill_type,"bill_number":watch.bill_number,
        "active":watch.active,"auto_research":watch.auto_research,
        "auto_report":watch.auto_report,"metadata":watch.metadata_json,
        "created_at":watch.created_at.isoformat() if watch.created_at else None,
        "last_scanned_at":watch.last_scanned_at.isoformat() if watch.last_scanned_at else None,
    }
