from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db.base import Base
from app.db.session import engine, get_db
from app.models.entities import Bill, BillVersion, Section, Finding
from app.services.ingest import ingest_federal
from app.services.diffing import summary, unified
from app.services.llm import deep_dive

Base.metadata.create_all(engine)
app=FastAPI(title="LegisWatch",version="0.1.0")

@app.get("/health")
def health(): return {"ok":True}

@app.post("/ingest/federal/{congress}/{bill_type}/{number}")
def ingest(congress:int,bill_type:str,number:str,db:Session=Depends(get_db)):
    try: return ingest_federal(db,congress,bill_type,number)
    except Exception as e: raise HTTPException(502,str(e))

@app.get("/bills")
def bills(db:Session=Depends(get_db)):
    return [{"id":b.id,"congress":b.congress,"bill_type":b.bill_type,"bill_number":b.bill_number,"title":b.title,"latest_action":b.latest_action} for b in db.scalars(select(Bill).order_by(Bill.id.desc())).all()]

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
    packed=[{"kind":f.kind,"evidence":f.evidence} for f in fs]
    try: analysis=deep_dive(bill.title or f"{bill.bill_type} {bill.bill_number}",sec.text,packed)
    except Exception as e: raise HTTPException(502,f"Local LLM failed: {e}")
    return {"bill":bill.title,"version":version.version_code,"section":sec.section_number,"analysis":analysis}
