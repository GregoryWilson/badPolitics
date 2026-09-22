from app.services.congress import CongressClient
from app.services.ingest import ingest_federal
BILL_TYPES={"HR":"hr","S":"s","HJRES":"hjres","SJRES":"sjres","HCONRES":"hconres","SCONRES":"sconres","HRES":"hres","SRES":"sres"}

def poll_recent_bills(db,congress:int,limit:int=50):
    payload=CongressClient().recently_updated(congress,limit=limit)
    results=[]
    for item in payload.get("bills",[]):
        number=item.get("number"); mapped=BILL_TYPES.get((item.get("type") or "").upper())
        if not number or not mapped: continue
        try: results.append(ingest_federal(db,congress,mapped,str(number)))
        except Exception as exc: results.append({"bill_type":mapped,"bill_number":str(number),"error":str(exc)})
    return results
