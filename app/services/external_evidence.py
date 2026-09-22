import hashlib
from sqlalchemy import select
from app.models.entities import EvidenceEntity, ExternalEvidenceRecord
from app.services.graph import get_or_create_entity, create_relationship
from app.services.fec import FECClient
from app.services.lda import LDAClient

def _record_id(value, fallback):
    return str(value or fallback)

def store_record(db, source_system:str, record_type:str, external_id:str, raw_json:dict, observed_on:str|None=None, source_url:str|None=None):
    record=db.scalar(select(ExternalEvidenceRecord).where(
        ExternalEvidenceRecord.source_system==source_system,
        ExternalEvidenceRecord.record_type==record_type,
        ExternalEvidenceRecord.external_id==external_id,
    ))
    if record:
        record.raw_json=raw_json
        record.observed_on=observed_on or record.observed_on
        record.source_url=source_url or record.source_url
        return record
    record=ExternalEvidenceRecord(source_system=source_system,record_type=record_type,external_id=external_id,observed_on=observed_on,source_url=source_url,raw_json=raw_json)
    db.add(record); db.flush(); return record

def import_fec_candidate(db, person_entity_id:int, candidate_id:str, cycle:int|None=None):
    person=db.get(EvidenceEntity,person_entity_id)
    if not person: raise ValueError("Person entity not found")
    client=FECClient()
    results=client._get(f"/candidate/{candidate_id}/",{"cycle":cycle}).get("results",[])
    if not results: raise ValueError("FEC candidate not found")
    candidate=results[0]
    store_record(db,"fec","candidate",candidate_id,candidate,source_url=f"https://www.fec.gov/data/candidate/{candidate_id}/")
    person.external_ids={**(person.external_ids or {}),"fec_candidate_id":candidate_id}
    if candidate.get("name"): person.metadata_json={**(person.metadata_json or {}),"fec_name":candidate.get("name")}
    committees=client.candidate_committees(candidate_id,cycle).get("results",[])
    linked=[]
    for item in committees:
        committee_id=item.get("committee_id")
        if not committee_id: continue
        committee=get_or_create_entity(db,"committee",item.get("name") or committee_id,external_ids={"fec_committee_id":committee_id},metadata={"designation":item.get("designation_full") or item.get("designation"),"committee_type":item.get("committee_type_full") or item.get("committee_type")})
        store_record(db,"fec","committee",committee_id,item,source_url=f"https://www.fec.gov/data/committee/{committee_id}/")
        rel=create_relationship(db,person.id,committee.id,"fec_candidate_committee",evidence=f"FEC records associate candidate {candidate_id} with committee {committee_id}.",source_url=f"https://www.fec.gov/data/committee/{committee_id}/",confidence=1.0,source_system="fec",metadata={"candidate_id":candidate_id,"committee_id":committee_id})
        linked.append({"committee_entity_id":committee.id,"committee_id":committee_id,"relationship_id":rel.id})
    db.commit()
    return {"person_entity_id":person.id,"candidate_id":candidate_id,"committees":linked}

def import_fec_receipts(db, committee_entity_id:int, committee_id:str, contributor_name:str, min_date:str|None=None, max_date:str|None=None):
    committee=db.get(EvidenceEntity,committee_entity_id)
    if not committee: raise ValueError("Committee entity not found")
    payload=FECClient().committee_receipts_by_contributor(committee_id,contributor_name,min_date,max_date)
    results=payload.get("results",[])
    imported=[]
    for i,item in enumerate(results):
        contributor=item.get("contributor_name") or contributor_name
        contributor_entity=get_or_create_entity(db,"organization",contributor,metadata={"fec_contributor_type":item.get("entity_type_desc")})
        fallback=":".join([committee_id,contributor,str(item.get("contribution_receipt_date")),str(item.get("contribution_receipt_amount")),str(i)])
        transaction_id=_record_id(item.get("sub_id") or item.get("transaction_id"),hashlib.sha256(fallback.encode()).hexdigest()[:24])
        source_url="https://www.fec.gov/data/receipts/"
        store_record(db,"fec","schedule_a_receipt",transaction_id,item,observed_on=item.get("contribution_receipt_date"),source_url=source_url)
        amount=item.get("contribution_receipt_amount"); date=item.get("contribution_receipt_date")
        evidence=f"FEC Schedule A reports a receipt from {contributor} to committee {committee_id}"
        if amount is not None: evidence += f" of ${amount}"
        if date: evidence += f" on {date}"
        evidence += "."
        rel=create_relationship(db,contributor_entity.id,committee.id,"fec_reported_receipt",evidence=evidence,source_url=source_url,observed_on=date,confidence=1.0,source_system="fec",metadata={"amount":amount,"committee_id":committee_id,"record_id":transaction_id})
        imported.append({"record_id":transaction_id,"contributor_entity_id":contributor_entity.id,"relationship_id":rel.id,"amount":amount,"date":date})
    db.commit()
    return {"committee_entity_id":committee.id,"committee_id":committee_id,"receipt_count":len(imported),"receipts":imported}

def import_lda_client(db, client_name:str, filing_year:int|None=None, max_records:int=100):
    payload=LDAClient().filings(client_name=client_name,filing_year=filing_year)
    results=payload.get("results",[])[:max_records]
    imported=[]
    for i,item in enumerate(results):
        client_data=item.get("client") or {}
        registrant_data=item.get("registrant") or {}
        actual_client=client_data.get("name") or client_name
        registrant_name=registrant_data.get("name") or "Unknown registrant"
        client_entity=get_or_create_entity(db,"organization",actual_client,external_ids={"lda_client_id":str(client_data.get("id"))} if client_data.get("id") else {})
        registrant_entity=get_or_create_entity(db,"lobbying_registrant",registrant_name,external_ids={"lda_registrant_id":str(registrant_data.get("id"))} if registrant_data.get("id") else {})
        fallback=f"{actual_client}:{registrant_name}:{item.get('filing_year')}:{item.get('filing_period')}:{i}"
        filing_uuid=_record_id(item.get("filing_uuid") or item.get("uuid"),hashlib.sha256(fallback.encode()).hexdigest()[:24])
        source_url=f"https://lda.gov/filings/public/filing/{filing_uuid}/print/"
        observed=item.get("dt_posted") or item.get("filing_date")
        store_record(db,"lda","filing",filing_uuid,item,observed_on=observed,source_url=source_url)
        activities=item.get("lobbying_activities") or []
        issues=[]
        for activity in activities:
            specific=activity.get("description") or activity.get("specific_issues")
            if specific: issues.append(specific)
        amount=item.get("income") or item.get("expenses") or item.get("amount")
        rel=create_relationship(db,registrant_entity.id,client_entity.id,"lda_registered_to_lobby_for",evidence=f"LDA filing {filing_uuid} identifies {registrant_name} as registrant for {actual_client}.",source_url=source_url,observed_on=observed,confidence=1.0,source_system="lda",metadata={"filing_uuid":filing_uuid,"filing_year":item.get("filing_year"),"filing_period":item.get("filing_period"),"amount":amount,"issues":issues})
        imported.append({"filing_uuid":filing_uuid,"client_entity_id":client_entity.id,"registrant_entity_id":registrant_entity.id,"relationship_id":rel.id,"amount":amount,"issues":issues})
    db.commit()
    return {"client_name":client_name,"filing_year":filing_year,"filing_count":len(imported),"filings":imported}