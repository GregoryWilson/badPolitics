import httpx
from app.core.config import settings
BASE="https://api.congress.gov/v3"

class CongressClient:
    def __init__(self): self.client=httpx.Client(timeout=30,follow_redirects=True)
    def _get(self,path:str,params:dict|None=None):
        if not settings.congress_api_key: raise RuntimeError("CONGRESS_API_KEY is required")
        q={"api_key":settings.congress_api_key,"format":"json"}
        if params: q.update(params)
        r=self.client.get(BASE+path,params=q); r.raise_for_status(); return r.json()
    def bill(self,c,t,n): return self._get(f"/bill/{c}/{t.lower()}/{n}")
    def text_versions(self,c,t,n): return self._get(f"/bill/{c}/{t.lower()}/{n}/text")
    def actions(self,c,t,n): return self._get(f"/bill/{c}/{t.lower()}/{n}/actions",{"limit":250})
    def cosponsors(self,c,t,n): return self._get(f"/bill/{c}/{t.lower()}/{n}/cosponsors",{"limit":250})
    def amendments(self,c,t,n): return self._get(f"/bill/{c}/{t.lower()}/{n}/amendments",{"limit":250})
    def recently_updated(self,c,limit=100,offset=0): return self._get(f"/bill/{c}",{"limit":limit,"offset":offset,"sort":"updateDate+desc"})
    def download_preferred_text(self,v):
        formats=v.get("formats") or []
        preferred=sorted(formats,key=lambda f:{"Formatted XML":0,"Formatted Text":1,"PDF":2}.get(f.get("type",""),9))
        for f in preferred:
            url=f.get("url")
            if not url: continue
            r=self.client.get(url,timeout=60)
            if r.is_success: return r.text,url,f.get("type")
        raise RuntimeError("No downloadable text format found")
