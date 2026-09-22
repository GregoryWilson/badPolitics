import httpx
from app.core.config import settings

class LDAClient:
    def __init__(self):
        self.client=httpx.Client(timeout=30,follow_redirects=True)

    def _get(self,path:str,params:dict|None=None):
        headers={}
        if settings.lda_api_key:
            headers["Authorization"]=f"Token {settings.lda_api_key}"
        r=self.client.get(
            settings.lda_base_url.rstrip("/")+"/"+path.lstrip("/"),
            params={k:v for k,v in (params or {}).items() if v is not None},
            headers=headers,
        )
        r.raise_for_status()
        return r.json()

    def filings(self,client_name:str|None=None,registrant_name:str|None=None,
                filing_year:int|None=None,filing_type:str|None=None,
                lobbying_issue:str|None=None):
        return self._get("/filings/",{
            "client_name":client_name,
            "registrant_name":registrant_name,
            "filing_year":filing_year,
            "filing_type":filing_type,
            "lobbying_activities__general_issue_code":lobbying_issue,
        })
