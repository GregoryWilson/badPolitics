import httpx
from app.core.config import settings

BASE = "https://api.congress.gov/v3"

class CongressClient:
    def __init__(self): self.client = httpx.Client(timeout=30)
    def _get(self, path: str):
        if not settings.congress_api_key:
            raise RuntimeError("CONGRESS_API_KEY is required")
        r = self.client.get(BASE + path, params={"api_key": settings.congress_api_key, "format":"json"})
        r.raise_for_status(); return r.json()
    def bill(self, congress:int, bill_type:str, number:str):
        return self._get(f"/bill/{congress}/{bill_type.lower()}/{number}")
    def text_versions(self, congress:int, bill_type:str, number:str):
        return self._get(f"/bill/{congress}/{bill_type.lower()}/{number}/text")
    def download_preferred_text(self, version:dict):
        formats = version.get("formats") or []
        preferred = sorted(formats, key=lambda f: {"Formatted XML":0,"Formatted Text":1,"PDF":2}.get(f.get("type",""), 9))
        for f in preferred:
            url = f.get("url")
            if not url: continue
            r = self.client.get(url, timeout=60, follow_redirects=True)
            if r.is_success:
                return r.text, url, f.get("type")
        raise RuntimeError("No downloadable text format found")
