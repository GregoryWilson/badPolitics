from fastapi import FastAPI,Depends,HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db.base import Base
from app.db.session import engine,get_db
from app.models.entities import Bill,BillVersion,Section,Finding,BillAction,BillSponsor,Amendment,EvidenceEntity
from app.services.ingest import ingest_federal
from app.services.monitor import poll_recent_bills
from app.services.diffing import summary,unified
from app.services.llm import deep_dive
from app.services.graph import sync_bill_graph,graph_for_bill,relationships_for_bill,create_relationship,get_or_create_entity
from app.schemas.graph import EntityCreate,RelationshipCreate
from app.services.metrics import bill_metrics

Base.metadata.create_all(engine)
app=FastAPI(title="LegisWatch",version="0.4.0")

@app.get("/health")
def health(): return {"ok":True,"version":"0.4.0"}

@app.post("/ingest/federal/{congress}/{bill_type}/{number}")
def ingest(congress:int,bill_type:str,number:str,db:Session=Depends(get_db)):
    try: return ingest_federal(db,congress,bill_type,number)
    except Exception as e: raise HTTPException(502,str(e))

@app.post("/monitor/federal/{congress}")
def monitor(congress:int,limit:int=50,db:Session=Depends(get_db)):
    try: return {"results":poll_recent_bills(db,congress,limit)}
    except Exception as e: raise HTTPException(502,str(e))

@app.get("/bills")
def bills(db:Session=Depends(get_db)):
    return [{"id":b.id,"congress":b.congress,"bill_type":b.bill_type,"bill_number":b.bill_number,"title":b.title,"latest_action":b.latest_action} for b in db.scalars(select(Bill).order_by(Bill.id.desc())).all()]

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
    versions=db.scalars(select(BillVersion).where(BillVersion.bill_id==bill_id).order_by(BillVersion.id.desc())).all()
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
def graph_get(bill_id:int,db:Session=Depends(get_db)):
    if not db.get(Bill,bill_id): raise HTTPException(404,"Bill not found")
    graph=graph_for_bill(db,bill_id)
    graph["relationships"]=relationships_for_bill(db,bill_id)
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
