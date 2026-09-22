import hashlib
from sqlalchemy import select

from app.models.entities import (
    Bill, BillVersion, Section, Finding, BillAction, BillSponsor, Amendment,
    LegislativeDocument,
)
from app.services.parser import normalize_text, split_sections
from app.services.rules import analyze_section
from app.services.graph import sync_bill_graph
from app.jurisdictions import get_adapter
from app.jurisdictions.base import NormalizedBill

def _upsert_action(db,bill,action):
    existing=db.scalar(select(BillAction).where(
        BillAction.bill_id==bill.id,
        BillAction.action_date==action.date,
        BillAction.text==action.text,
    ))
    if existing:
        return existing,False
    row=BillAction(
        bill_id=bill.id,
        action_date=action.date,
        text=action.text,
        action_code=action.code,
        source_url=action.source_url,
        raw_json=action.raw,
    )
    db.add(row); db.flush()
    return row,True

def _upsert_sponsor(db,bill,sponsor):
    q=select(BillSponsor).where(
        BillSponsor.bill_id==bill.id,
        BillSponsor.role==sponsor.role,
    )
    if sponsor.external_id:
        q=q.where(BillSponsor.bioguide_id==sponsor.external_id)
    else:
        q=q.where(BillSponsor.full_name==sponsor.name)
    existing=db.scalar(q)
    if existing:
        existing.party=sponsor.party
        existing.state=sponsor.state
        existing.district=sponsor.district
        existing.raw_json=sponsor.raw
        return
    db.add(BillSponsor(
        bill_id=bill.id,
        bioguide_id=sponsor.external_id,
        full_name=sponsor.name,
        party=sponsor.party,
        state=sponsor.state,
        district=sponsor.district,
        role=sponsor.role,
        raw_json=sponsor.raw,
    ))

def _upsert_amendment(db,bill,data,amendment):
    existing=db.scalar(select(Amendment).where(
        Amendment.bill_id==bill.id,
        Amendment.amendment_type==amendment.amendment_type,
        Amendment.amendment_number==amendment.amendment_number,
    ))
    if existing:
        existing.description=amendment.description
        existing.latest_action=amendment.latest_action
        existing.source_url=amendment.source_url
        existing.raw_json=amendment.raw
        return
    db.add(Amendment(
        bill_id=bill.id,
        congress=data.session_number,
        amendment_type=amendment.amendment_type,
        amendment_number=amendment.amendment_number,
        description=amendment.description,
        latest_action=amendment.latest_action,
        source_url=amendment.source_url,
        raw_json=amendment.raw,
    ))

def _upsert_document(db,bill,data,document):
    text=normalize_text(document.text) if document.text else None
    sha=hashlib.sha256(text.encode()).hexdigest() if text else None
    existing=db.scalar(select(LegislativeDocument).where(
        LegislativeDocument.bill_id==bill.id,
        LegislativeDocument.document_type==document.document_type,
        LegislativeDocument.source_url==document.source_url,
    ))
    if existing:
        existing.description=document.description
        existing.issued_on=document.issued_on
        existing.format=document.format
        existing.text=text
        existing.sha256=sha
        existing.metadata_json=document.metadata
        return existing,False
    row=LegislativeDocument(
        bill_id=bill.id,
        document_type=document.document_type,
        description=document.description,
        source_url=document.source_url,
        source_system=data.source_system,
        issued_on=document.issued_on,
        format=document.format,
        text=text,
        sha256=sha,
        metadata_json=document.metadata,
    )
    db.add(row); db.flush()
    return row,True

def ingest_normalized_bill(db,data:NormalizedBill):
    bill=db.scalar(select(Bill).where(
        Bill.jurisdiction==data.jurisdiction,
        Bill.congress==data.session_number,
        Bill.bill_type==data.bill_type.lower(),
        Bill.bill_number==str(data.bill_number),
    ))
    if not bill:
        bill=Bill(
            jurisdiction=data.jurisdiction,
            congress=data.session_number,
            bill_type=data.bill_type.lower(),
            bill_number=str(data.bill_number),
        )
        db.add(bill)

    metadata=dict(data.metadata or {})
    metadata.update({
        "jurisdiction_session":data.session,
        "source_url":data.source_url,
        "source_system":data.source_system,
    })
    bill.title=data.title
    bill.latest_action=data.latest_action
    bill.metadata_json=metadata
    db.flush()

    created=[]
    for version in data.versions:
        if version.text is None:
            continue
        text=normalize_text(version.text)
        sha=hashlib.sha256(text.encode()).hexdigest()
        existing=db.scalar(select(BillVersion).where(
            BillVersion.bill_id==bill.id,
            BillVersion.version_code==version.code,
            BillVersion.sha256==sha,
        ))
        if existing:
            continue
        row=BillVersion(
            bill_id=bill.id,
            version_code=version.code,
            version_name=version.name,
            source_url=version.source_url,
            source_system=data.source_system,
            issued_on=version.issued_on,
            text=text,
            sha256=sha,
        )
        db.add(row); db.flush()
        for section in split_sections(text):
            sec=Section(
                version_id=row.id,
                section_number=section["number"],
                heading=section["heading"],
                text=section["text"],
                ordinal=section["ordinal"],
            )
            db.add(sec); db.flush()
            for finding in analyze_section(section):
                db.add(Finding(
                    version_id=row.id,
                    section_id=sec.id,
                    kind=finding["kind"],
                    severity=finding["severity"],
                    label=finding["label"],
                    evidence=finding["evidence"],
                    metadata_json=finding.get("metadata",{}),
                ))
        created.append({
            "version":version.code,
            "sha256":sha,
            "source_url":version.source_url,
            "format":version.format,
        })

    created_actions=[]
    for action in data.actions:
        row,is_new=_upsert_action(db,bill,action)
        if is_new:
            created_actions.append({
                "id":row.id,
                "date":row.action_date,
                "text":row.text,
                "code":row.action_code,
            })
    for sponsor in data.sponsors:
        _upsert_sponsor(db,bill,sponsor)
    for amendment in data.amendments:
        _upsert_amendment(db,bill,data,amendment)
    created_documents=[]
    for document in data.documents:
        row,is_new=_upsert_document(db,bill,data,document)
        if is_new:
            created_documents.append({
                "id":row.id,
                "document_type":row.document_type,
                "description":row.description,
                "source_url":row.source_url,
                "sha256":row.sha256,
            })

    db.commit()
    graph_error=None
    try:
        sync_bill_graph(db,bill.id)
    except Exception as exc:
        graph_error=str(exc)

    return {
        "bill_id":bill.id,
        "jurisdiction":data.jurisdiction,
        "session":data.session,
        "title":bill.title,
        "created_versions":created,
        "created_actions":created_actions,
        "documents":created_documents,
        "graph_sync_error":graph_error,
    }

def ingest_jurisdiction(db,jurisdiction:str,session:str,bill_type:str,number:str):
    adapter=get_adapter(jurisdiction)
    data=adapter.fetch_bill(session,bill_type,number)
    return ingest_normalized_bill(db,data)

def ingest_federal(db,congress:int,bill_type:str,number:str):
    return ingest_jurisdiction(db,"US",str(congress),bill_type,number)


def discover_jurisdiction(db,jurisdiction:str,session:str,limit:int=100,ingest:bool=False):
    adapter=get_adapter(jurisdiction)
    discover=getattr(adapter,"discover_bills",None)
    if not discover:
        raise ValueError(f"Jurisdiction {jurisdiction.upper()} does not support session discovery")
    result=discover(session,limit=limit)
    if not ingest:
        return result
    ingested=[]
    failed=[]
    for item in result.get("bills",[]):
        try:
            ingested.append(ingest_jurisdiction(
                db,jurisdiction,session,item["bill_type"],item["number"]
            ))
        except Exception as exc:
            failed.append({
                "bill_type":item.get("bill_type"),
                "number":item.get("number"),
                "error":str(exc),
            })
    return {**result,"ingested":ingested,"failed":failed}
