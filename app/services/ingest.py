import hashlib
from sqlalchemy import select
from app.models.entities import Bill, BillVersion, Section, Finding
from app.services.congress import CongressClient
from app.services.parser import normalize_text, split_sections
from app.services.rules import analyze_section

def ingest_federal(db, congress:int, bill_type:str, number:str):
    c=CongressClient(); meta=c.bill(congress,bill_type,number); payload=meta.get("bill",meta)
    bill=db.scalar(select(Bill).where(Bill.jurisdiction=="US", Bill.congress==congress, Bill.bill_type==bill_type.lower(), Bill.bill_number==str(number)))
    if not bill:
        bill=Bill(jurisdiction="US",congress=congress,bill_type=bill_type.lower(),bill_number=str(number)); db.add(bill)
    bill.title=payload.get("title"); bill.latest_action=(payload.get("latestAction") or {}).get("text"); bill.metadata_json=payload; db.flush()
    tv=c.text_versions(congress,bill_type,number)
    versions=tv.get("textVersions") or tv.get("text", {}).get("textVersions") or []
    created=[]
    for v in versions:
        raw,url,fmt=c.download_preferred_text(v); text=normalize_text(raw); sha=hashlib.sha256(text.encode()).hexdigest()
        code=v.get("type") or v.get("typeCode") or v.get("name") or "unknown"
        exists=db.scalar(select(BillVersion).where(BillVersion.bill_id==bill.id,BillVersion.version_code==code,BillVersion.sha256==sha))
        if exists: continue
        bv=BillVersion(bill_id=bill.id,version_code=code,version_name=v.get("name"),source_url=url,issued_on=v.get("date"),text=text,sha256=sha); db.add(bv); db.flush()
        for s in split_sections(text):
            sec=Section(version_id=bv.id,section_number=s["number"],heading=s["heading"],text=s["text"],ordinal=s["ordinal"]); db.add(sec); db.flush()
            for f in analyze_section(s): db.add(Finding(version_id=bv.id,section_id=sec.id,kind=f["kind"],severity=f["severity"],label=f["label"],evidence=f["evidence"],metadata_json=f.get("metadata",{})))
        created.append({"version":code,"sha256":sha,"source_url":url})
    db.commit(); return {"bill_id":bill.id,"title":bill.title,"created_versions":created}
