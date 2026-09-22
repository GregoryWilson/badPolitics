from datetime import datetime
from sqlalchemy import select
from app.models.entities import (
    Bill, BillVersion, BillAction, Amendment,
    WatchRule, WatchScan, WatchEvent,
)
from app.services.ingest import ingest_federal
from app.services.monitor import poll_recent_bills
from app.services.research import run_bill_research
from app.services.reporting import build_report

def _bill_key(congress,bill_type,bill_number):
    return f"{congress}:{bill_type.lower()}:{bill_number}"

def _find_bill(db,congress,bill_type,bill_number):
    return db.scalar(select(Bill).where(
        Bill.jurisdiction=="US",
        Bill.congress==congress,
        Bill.bill_type==bill_type.lower(),
        Bill.bill_number==str(bill_number),
    ))

def _snapshot_bill(db,bill):
    if not bill:
        return {"exists":False,"versions":set(),"actions":set(),"amendments":set()}
    versions=set(db.scalars(select(BillVersion.sha256).where(BillVersion.bill_id==bill.id)).all())
    actions=set(
        f"{a.action_date}|{a.text}"
        for a in db.scalars(select(BillAction).where(BillAction.bill_id==bill.id)).all()
    )
    amendments=set(
        f"{a.amendment_type}|{a.amendment_number}"
        for a in db.scalars(select(Amendment).where(Amendment.bill_id==bill.id)).all()
    )
    return {"exists":True,"versions":versions,"actions":actions,"amendments":amendments}

def _emit(db,watch,scan,bill,event_type,event_key,title,detail):
    existing=db.scalar(select(WatchEvent).where(
        WatchEvent.watch_rule_id==watch.id,
        WatchEvent.event_type==event_type,
        WatchEvent.event_key==event_key,
    ))
    if existing:
        return None
    row=WatchEvent(
        watch_rule_id=watch.id,
        watch_scan_id=scan.id,
        bill_id=bill.id if bill else None,
        event_type=event_type,
        event_key=event_key,
        title=title,
        detail_json=detail,
    )
    db.add(row); db.flush()
    return row

def _diff_events(db,watch,scan,bill,before,after):
    events=[]
    for sha in sorted(after["versions"]-before["versions"]):
        row=_emit(
            db,watch,scan,bill,"new_version",sha,
            f"New bill text version detected for {bill.bill_type.upper()} {bill.bill_number}",
            {"sha256":sha},
        )
        if row: events.append(row)
    for key in sorted(after["actions"]-before["actions"]):
        date,text=key.split("|",1)
        row=_emit(
            db,watch,scan,bill,"new_action",key,
            f"New legislative action for {bill.bill_type.upper()} {bill.bill_number}",
            {"action_date":date or None,"text":text},
        )
        if row: events.append(row)
    for key in sorted(after["amendments"]-before["amendments"]):
        amendment_type,number=key.split("|",1)
        row=_emit(
            db,watch,scan,bill,"new_amendment",key,
            f"New amendment for {bill.bill_type.upper()} {bill.bill_number}",
            {"amendment_type":amendment_type,"amendment_number":number},
        )
        if row: events.append(row)
    return events

def _refresh_outputs(db,watch,bill,events):
    result={}
    if not events:
        return result
    if watch.auto_research:
        research=run_bill_research(db,bill.id)
        result["research_run_id"]=research["run"]["id"]
        result["research_status"]=research["run"]["status"]
    if watch.auto_report:
        report=build_report(db,bill.id,result.get("research_run_id"))
        result["report_id"]=report["report_id"]
    return result

def scan_bill_watch(db,watch,scan):
    bill=_find_bill(db,watch.congress,watch.bill_type,watch.bill_number)
    before=_snapshot_bill(db,bill)
    ingest_result=ingest_federal(db,watch.congress,watch.bill_type,watch.bill_number)
    bill=_find_bill(db,watch.congress,watch.bill_type,watch.bill_number)
    after=_snapshot_bill(db,bill)
    events=[]
    if not before["exists"] and bill:
        row=_emit(
            db,watch,scan,bill,"bill_discovered",_bill_key(watch.congress,watch.bill_type,watch.bill_number),
            f"Bill added to local store: {bill.bill_type.upper()} {bill.bill_number}",
            {"title":bill.title},
        )
        if row: events.append(row)
    if before["exists"]:
        events.extend(_diff_events(db,watch,scan,bill,before,after))
    refreshed=_refresh_outputs(db,watch,bill,events)
    return {
        "bill_id":bill.id if bill else None,
        "ingest":ingest_result,
        "new_event_ids":[e.id for e in events],
        "refreshed":refreshed,
    }

def scan_congress_watch(db,watch,scan):
    before_bills=db.scalars(select(Bill).where(
        Bill.jurisdiction=="US",Bill.congress==watch.congress
    )).all()
    before={bill.id:_snapshot_bill(db,bill) for bill in before_bills}
    before_ids=set(before)
    results=poll_recent_bills(db,watch.congress,limit=int((watch.metadata_json or {}).get("limit",50)))
    after_bills=db.scalars(select(Bill).where(
        Bill.jurisdiction=="US",Bill.congress==watch.congress
    )).all()
    events=[]
    refreshed={}
    for bill in after_bills:
        after=_snapshot_bill(db,bill)
        bill_events=[]
        if bill.id not in before_ids:
            key=_bill_key(bill.congress,bill.bill_type,bill.bill_number)
            row=_emit(
                db,watch,scan,bill,"bill_discovered",key,
                f"Newly monitored bill: {bill.bill_type.upper()} {bill.bill_number}",
                {"title":bill.title,"latest_action":bill.latest_action},
            )
            if row:
                events.append(row); bill_events.append(row)
        else:
            bill_events=_diff_events(db,watch,scan,bill,before[bill.id],after)
            events.extend(bill_events)
        if bill_events and (watch.auto_research or watch.auto_report):
            refreshed[str(bill.id)]=_refresh_outputs(db,watch,bill,bill_events)
    return {
        "poll_result_count":len(results),
        "new_event_ids":[e.id for e in events],
        "refreshed":refreshed,
    }

def run_watch(db,watch_id:int):
    watch=db.get(WatchRule,watch_id)
    if not watch:
        raise ValueError("Watch rule not found")
    if not watch.active:
        raise ValueError("Watch rule is inactive")
    scan=WatchScan(watch_rule_id=watch.id,status="running")
    db.add(scan); db.flush()
    try:
        if watch.target_type=="bill":
            result=scan_bill_watch(db,watch,scan)
        elif watch.target_type=="congress":
            result=scan_congress_watch(db,watch,scan)
        else:
            raise ValueError(f"Unsupported watch target type: {watch.target_type}")
        scan.status="completed"
        scan.completed_at=datetime.utcnow()
        scan.summary_json=result
        watch.last_scanned_at=scan.completed_at
        db.commit()
        return get_scan(db,scan.id)
    except Exception as exc:
        scan.status="failed"
        scan.completed_at=datetime.utcnow()
        scan.summary_json={"error":str(exc)}
        watch.last_scanned_at=scan.completed_at
        db.commit()
        raise

def run_active_watches(db):
    watches=db.scalars(select(WatchRule).where(WatchRule.active==True).order_by(WatchRule.id)).all()
    results=[]
    for watch in watches:
        try:
            results.append(run_watch(db,watch.id))
        except Exception as exc:
            results.append({"watch_rule_id":watch.id,"status":"failed","error":str(exc)})
    return results

def get_scan(db,scan_id:int):
    scan=db.get(WatchScan,scan_id)
    if not scan:
        raise ValueError("Watch scan not found")
    events=db.scalars(select(WatchEvent).where(WatchEvent.watch_scan_id==scan.id).order_by(WatchEvent.id)).all()
    return {
        "id":scan.id,
        "watch_rule_id":scan.watch_rule_id,
        "status":scan.status,
        "started_at":scan.started_at.isoformat() if scan.started_at else None,
        "completed_at":scan.completed_at.isoformat() if scan.completed_at else None,
        "summary":scan.summary_json,
        "events":[{
            "id":e.id,"bill_id":e.bill_id,"event_type":e.event_type,
            "title":e.title,"detail":e.detail_json,
            "created_at":e.created_at.isoformat() if e.created_at else None,
        } for e in events],
    }

def list_events(db,watch_rule_id:int|None=None,limit:int=100):
    q=select(WatchEvent).order_by(WatchEvent.id.desc()).limit(max(1,min(limit,500)))
    if watch_rule_id is not None:
        q=q.where(WatchEvent.watch_rule_id==watch_rule_id)
    rows=db.scalars(q).all()
    return [{
        "id":e.id,"watch_rule_id":e.watch_rule_id,"watch_scan_id":e.watch_scan_id,
        "bill_id":e.bill_id,"event_type":e.event_type,"title":e.title,
        "detail":e.detail_json,"created_at":e.created_at.isoformat() if e.created_at else None,
    } for e in rows]
