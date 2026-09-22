import httpx
from app.core.config import settings

BASE="https://api.open.fec.gov/v1"

class FECClient:
    def __init__(self):
        self.client=httpx.Client(timeout=30,follow_redirects=True)

    def _get(self,path:str,params:dict|None=None):
        key=settings.fec_api_key or "DEMO_KEY"
        q={"api_key":key,"per_page":100}
        if params:
            q.update({k:v for k,v in params.items() if v is not None})
        r=self.client.get(BASE+path,params=q)
        r.raise_for_status()
        return r.json()

    def candidate_search(self,name:str,election_year:int|None=None):
        return self._get("/candidates/search/",{
            "q":name,
            "election_year":election_year,
        })

    def candidate_committees(self,candidate_id:str,cycle:int|None=None):
        return self._get(f"/candidate/{candidate_id}/committees/",{
            "cycle":cycle,
        })

    def committee_receipts_by_contributor(self,committee_id:str,contributor_name:str,
                                          min_date:str|None=None,max_date:str|None=None):
        return self._get("/schedules/schedule_a/",{
            "committee_id":committee_id,
            "contributor_name":contributor_name,
            "min_date":min_date,
            "max_date":max_date,
        })
