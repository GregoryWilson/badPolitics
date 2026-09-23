from datetime import datetime
from sqlalchemy import select

from app.core.config import settings
from app.models.entities import DiscoveryCursor, CivicDocument, CivicDocumentRevision
from app.services.congress import CongressClient
from app.services.ingest import ingest_jurisdiction
from app.services.monitor import BILL_TYPES
from app.jurisdictions import get_adapter
from app.services.civic_crawler import scan_civic_source
from app.services.civic_sources import CIVIC_SOURCES

def _cursor(db,source_key,jurisdiction,session=None):
    row=db.scalar(select(DiscoveryCursor).where(DiscoveryCursor.source_key==source_key))
    if row:
        return row
    row=DiscoveryCursor(
        source_key=source_key,
        jurisdiction=jurisdiction,
        session=session,
        cursor_json={"offset":0},
        cycle=1,
        status="idle",
        updated_at=datetime.utcnow(),
    )
    db.add(row); db.flush(); db.commit(); db.refresh(row)
    return row

def _finish_cursor(db,row,result,next_offset=None,complete=False):
    now=datetime.utcnow()
    row.status="idle"
    row.last_error=None
    row.last_completed_at=now
    row.updated_at=now
    state=dict(row.cursor_json or {})
    if complete:
        row.cycle=(row.cycle or 1)+1
        state["offset"]=0
    elif next_offset is not None:
        state["offset"]=next_offset
    state["last_result"]=result
    row.cursor_json=state
    db.commit()
    return result

def _fail_cursor(db,row,exc):
    row.status="error"
    row.last_error=str(exc)
    row.last_completed_at=datetime.utcnow()
    row.updated_at=row.last_completed_at
    db.commit()
    return {
        "source_key":row.source_key,
        "status":"error",
        "error":str(exc),
        "cycle":row.cycle,
        "cursor":row.cursor_json,
    }

def discover_federal_batch(db,congress=None,batch_size=None):
    congress=int(congress or settings.auto_discovery_us_congress)
    batch=max(1,min(int(batch_size or settings.auto_discovery_batch_size),250))
    source_key=f"legis:US:{congress}"
    cursor=_cursor(db,source_key,"US",str(congress))
    offset=int((cursor.cursor_json or {}).get("offset",0))
    cursor.status="running"; cursor.last_started_at=datetime.utcnow(); cursor.updated_at=cursor.last_started_at
    db.commit()
    try:
        payload=CongressClient().recently_updated(congress,limit=batch,offset=offset)
        items=payload.get("bills",[])
        ingested=[]; failed=[]; skipped=[]
        for item in items:
            number=item.get("number")
            mapped=BILL_TYPES.get((item.get("type") or "").upper())
            if not number or not mapped:
                skipped.append({"type":item.get("type"),"number":number})
                continue
            try:
                ingested.append(ingest_jurisdiction(db,"US",str(congress),mapped,str(number)))
            except Exception as exc:
                failed.append({"bill_type":mapped,"number":str(number),"error":str(exc)})
        pagination=payload.get("pagination") or {}
        total=pagination.get("count")
        next_offset=offset+len(items)
        complete=(not items) or (len(items)<batch) or (isinstance(total,int) and next_offset>=total)
        result={
            "source_key":source_key,
            "status":"completed",
            "jurisdiction":"US",
            "session":str(congress),
            "cycle":cursor.cycle,
            "offset":offset,
            "batch_size":batch,
            "source_count":len(items),
            "ingested_count":len(ingested),
            "failed_count":len(failed),
            "skipped_count":len(skipped),
            "next_offset":0 if complete else next_offset,
            "cycle_complete":complete,
            "reported_total":total,
            "failed":failed[:25],
        }
        return _finish_cursor(db,cursor,result,next_offset=next_offset,complete=complete)
    except Exception as exc:
        return _fail_cursor(db,cursor,exc)

def discover_texas_batch(db,session,batch_size=None):
    batch=max(1,min(int(batch_size or settings.auto_discovery_batch_size),500))
    source_key=f"legis:TX:{session.upper()}"
    cursor=_cursor(db,source_key,"TX",session.upper())
    offset=int((cursor.cursor_json or {}).get("offset",0))
    cursor.status="running"; cursor.last_started_at=datetime.utcnow(); cursor.updated_at=cursor.last_started_at
    db.commit()
    try:
        adapter=get_adapter("TX")
        discovered=adapter.discover_bills(session,limit=batch,offset=offset)
        ingested=[]; failed=[]
        for item in discovered.get("bills",[]):
            try:
                ingested.append(ingest_jurisdiction(db,"TX",session,item["bill_type"],item["number"]))
            except Exception as exc:
                failed.append({"bill_type":item.get("bill_type"),"number":item.get("number"),"error":str(exc)})
        next_offset=discovered.get("next_offset")
        complete=next_offset is None
        result={
            "source_key":source_key,
            "status":"completed",
            "jurisdiction":"TX",
            "session":discovered.get("session") or session,
            "cycle":cursor.cycle,
            "offset":offset,
            "batch_size":batch,
            "source_count":len(discovered.get("bills",[])),
            "source_total":discovered.get("total"),
            "ingested_count":len(ingested),
            "failed_count":len(failed),
            "next_offset":0 if complete else next_offset,
            "cycle_complete":complete,
            "failed":failed[:25],
        }
        return _finish_cursor(db,cursor,result,next_offset=next_offset or 0,complete=complete)
    except Exception as exc:
        return _fail_cursor(db,cursor,exc)

def discover_civic_source(db,source_key,limit=None):
    source=next((s for s in CIVIC_SOURCES if s["source_key"]==source_key),None)
    if not source:
        raise ValueError(f"Unknown civic source: {source_key}")
    cursor=_cursor(db,f"civic:{source_key}",source["jurisdiction"],None)
    cursor.status="running"; cursor.last_started_at=datetime.utcnow(); cursor.updated_at=cursor.last_started_at
    db.commit()
    try:
        result=scan_civic_source(db,source_key,limit or settings.auto_discovery_batch_size)
        result={
            **result,
            "source_key":f"civic:{source_key}",
            "jurisdiction":source["jurisdiction"],
            "governing_body":source["governing_body"],
            "cycle":cursor.cycle,
            "status":"completed",
            "cycle_complete":True,
        }
        return _finish_cursor(db,cursor,result,complete=True)
    except Exception as exc:
        return _fail_cursor(db,cursor,exc)

def run_auto_discovery(db):
    results=[]
    results.append(discover_federal_batch(db))
    for session in [x.strip() for x in settings.auto_discovery_tx_sessions.split(",") if x.strip()]:
        results.append(discover_texas_batch(db,session))
    for source in CIVIC_SOURCES:
        results.append(discover_civic_source(db,source["source_key"]))
    return {
        "ran_at":datetime.utcnow().isoformat(),
        "result_count":len(results),
        "results":results,
    }

def discovery_status(db):
    rows=db.scalars(select(DiscoveryCursor).order_by(DiscoveryCursor.source_key)).all()
    return [{
        "source_key":row.source_key,
        "jurisdiction":row.jurisdiction,
        "session":row.session,
        "cycle":row.cycle,
        "status":row.status,
        "cursor":row.cursor_json,
        "last_started_at":row.last_started_at.isoformat() if row.last_started_at else None,
        "last_completed_at":row.last_completed_at.isoformat() if row.last_completed_at else None,
        "last_error":row.last_error,
        "updated_at":row.updated_at.isoformat() if row.updated_at else None,
    } for row in rows]

def list_civic_documents(db,source_key=None,governing_body=None,limit=200):
    q=select(CivicDocument).order_by(CivicDocument.last_seen_at.desc(),CivicDocument.id.desc())
    if source_key:
        q=q.where(CivicDocument.source_key==source_key)
    if governing_body:
        q=q.where(CivicDocument.governing_body==governing_body)
    rows=db.scalars(q.limit(max(1,min(limit,1000)))).all()
    return [{
        "id":row.id,
        "source_key":row.source_key,
        "jurisdiction":row.jurisdiction,
        "governing_body":row.governing_body,
        "document_type":row.document_type,
        "title":row.title,
        "meeting_date":row.meeting_date,
        "source_url":row.source_url,
        "sha256":row.sha256,
        "first_seen_at":row.first_seen_at.isoformat() if row.first_seen_at else None,
        "last_seen_at":row.last_seen_at.isoformat() if row.last_seen_at else None,
        "metadata":row.metadata_json,
    } for row in rows]

def civic_document_revisions(db,document_id):
    doc=db.get(CivicDocument,document_id)
    if not doc:
        raise ValueError("Civic document not found")
    rows=db.scalars(
        select(CivicDocumentRevision)
        .where(CivicDocumentRevision.civic_document_id==document_id)
        .order_by(CivicDocumentRevision.observed_at.desc(),CivicDocumentRevision.id.desc())
    ).all()
    return {
        "document_id":document_id,
        "title":doc.title,
        "source_url":doc.source_url,
        "revisions":[{
            "id":row.id,
            "sha256":row.sha256,
            "text":row.text,
            "metadata":row.metadata_json,
            "observed_at":row.observed_at.isoformat() if row.observed_at else None,
        } for row in rows],
    }
