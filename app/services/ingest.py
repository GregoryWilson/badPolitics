import hashlib
from sqlalchemy import select
from app.models.entities import Bill,BillVersion,Section,Finding,BillAction,BillSponsor,Amendment
from app.services.congress import CongressClient
from app.services.parser import normalize_text,split_sections
from app.services.rules import analyze_section
from app.services.graph import sync_bill_graph

def _upsert_related(db,bill,c,congress,bill_type,number):
    for a in c.actions(congress,bill_type,number).get("actions",[]):
        text=a.get("text") or ""; dt=a.get("actionDate")
        if not db.scalar(select(BillAction).where(BillAction.bill_id==bill.id,BillAction.action_date==dt,BillAction.text==text)):
            db.add(BillAction(bill_id=bill.id,action_date=dt,text=text,action_code=a.get("actionCode"),raw_json=a))
    for role,rows in (("sponsor",(bill.metadata_json or {}).get("sponsors") or []),("cosponsor",c.cosponsors(congress,bill_type,number).get("cosponsors",[]))):
        for s in rows:
            bio=s.get("bioguideId")
            if not db.scalar(select(BillSponsor).where(BillSponsor.bill_id==bill.id,BillSponsor.bioguide_id==bio,BillSponsor.role==role)):
                db.add(BillSponsor(bill_id=bill.id,bioguide_id=bio,full_name=s.get("fullName") or s.get("name") or bio or "Unknown",party=s.get("party"),state=s.get("state"),district=s.get("district"),role=role,raw_json=s))
    for a in c.amendments(congress,bill_type,number).get("amendments",[]):
        at=(a.get("type") or "unknown").lower(); an=str(a.get("number") or "")
        if an and not db.scalar(select(Amendment).where(Amendment.congress==congress,Amendment.amendment_type==at,Amendment.amendment_number==an)):
            db.add(Amendment(bill_id=bill.id,congress=congress,amendment_type=at,amendment_number=an,description=a.get("description"),latest_action=(a.get("latestAction") or {}).get("text"),source_url=a.get("url"),raw_json=a))

def ingest_federal(db,congress:int,bill_type:str,number:str):
    c=CongressClient(); meta=c.bill(congress,bill_type,number); payload=meta.get("bill",meta)
    bill=db.scalar(select(Bill).where(Bill.jurisdiction=="US",Bill.congress==congress,Bill.bill_type==bill_type.lower(),Bill.bill_number==str(number)))
    if not bill:
        bill=Bill(jurisdiction="US",congress=congress,bill_type=bill_type.lower(),bill_number=str(number)); db.add(bill)
    bill.title=payload.get("title"); bill.latest_action=(payload.get("latestAction") or {}).get("text"); bill.metadata_json=payload; db.flush()
    tv=c.text_versions(congress,bill_type,number)
    versions=tv.get("textVersions") or tv.get("text",{}).get("textVersions") or []
    created=[]
    for v in versions:
        raw,url,fmt=c.download_preferred_text(v); text=normalize_text(raw); sha=hashlib.sha256(text.encode()).hexdigest()
        code=v.get("type") or v.get("typeCode") or v.get("name") or "unknown"
        if db.scalar(select(BillVersion).where(BillVersion.bill_id==bill.id,BillVersion.version_code==code,BillVersion.sha256==sha)): continue
        bv=BillVersion(bill_id=bill.id,version_code=code,version_name=v.get("name"),source_url=url,source_system="congress",issued_on=v.get("date"),text=text,sha256=sha); db.add(bv); db.flush()
        for s in split_sections(text):
            sec=Section(version_id=bv.id,section_number=s["number"],heading=s["heading"],text=s["text"],ordinal=s["ordinal"]); db.add(sec); db.flush()
            for f in analyze_section(s): db.add(Finding(version_id=bv.id,section_id=sec.id,kind=f["kind"],severity=f["severity"],label=f["label"],evidence=f["evidence"],metadata_json=f.get("metadata",{})))
        created.append({"version":code,"sha256":sha,"source_url":url,"format":fmt})
    _upsert_related(db,bill,c,congress,bill_type,number); db.commit()
    graph_error=None
    try:
        sync_bill_graph(db,bill.id)
    except Exception as exc:
        graph_error=str(exc)
    return {"bill_id":bill.id,"title":bill.title,"created_versions":created,"graph_sync_error":graph_error}
