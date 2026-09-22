import httpx
from app.core.config import settings
BASE="https://api.govinfo.gov"

class GovInfoClient:
    def __init__(self): self.client=httpx.Client(timeout=45,follow_redirects=True)
    def _get(self,path,params=None):
        if not settings.govinfo_api_key: raise RuntimeError("GOVINFO_API_KEY is required")
        q={"api_key":settings.govinfo_api_key}
        if params: q.update(params)
        r=self.client.get(BASE+path,params=q); r.raise_for_status(); return r.json()
    def package_summary(self,package_id): return self._get(f"/packages/{package_id}/summary")
    def package_text(self,package_id):
        for suffix in ("xml","html","txt"):
            url=f"{BASE}/packages/{package_id}/{suffix}"
            r=self.client.get(url,params={"api_key":settings.govinfo_api_key})
            if r.is_success: return r.text,url,suffix
        raise RuntimeError(f"No text representation available for {package_id}")
