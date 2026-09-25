import httpx
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
import app.models.entities  # noqa: F401
from app.models.entities import DiscoveryCursor
from app.core.config import settings
from app.services.congress import CongressClient
from app.services.auto_discovery import discover_federal_batch
from app.services.source_dashboard import weekly_source_summary


def test_congress_updated_sort_uses_query_space_encoding(monkeypatch):
    seen=[]
    original_client=httpx.Client
    def respond(request):
        seen.append(str(request.url))
        return httpx.Response(200,json={"bills":[]})
    monkeypatch.setattr("app.services.congress.httpx.Client",
        lambda **kwargs:original_client(transport=httpx.MockTransport(respond),**kwargs))
    monkeypatch.setattr(settings,"congress_api_key","test-key")
    CongressClient().recently_updated(119,limit=2)
    assert "sort=updateDate+desc" in seen[0]
    assert "sort=updateDate%2Bdesc" not in seen[0]


def test_fixed_federal_sort_restarts_stale_discovery_offset(tmp_path,monkeypatch):
    engine=create_engine("sqlite:///"+str(tmp_path/"federal.db"))
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            db.add(DiscoveryCursor(source_key="legis:US:119",jurisdiction="US",
                session="119",cursor_json={"offset":5000},cycle=2,status="idle"))
            db.commit()
            requested=[]
            class FakeCongressClient:
                def recently_updated(self,congress,limit,offset):
                    requested.append(offset)
                    return {"bills":[{"number":"1","type":"HR","title":"School funding act",
                            "url":"https://api.congress.gov/v3/bill/119/hr/1",
                            "latestAction":{"actionDate":date.today().isoformat(),
                                            "text":"Referred to the Committee on Education."}}],
                            "pagination":{"count":50000}}
            monkeypatch.setattr("app.services.auto_discovery.CongressClient",FakeCongressClient)
            monkeypatch.setattr("app.services.auto_discovery.ingest_jurisdiction",
                                lambda *args: {"bill_id":1})
            result=discover_federal_batch(db,congress=119,batch_size=1)
            cursor=db.get(DiscoveryCursor,1)
            assert requested==[0]
            assert result["ingested_count"]==1
            assert result["weekly_actions_captured"]==1
            assert cursor.cursor_json["offset"]==1
            assert cursor.cursor_json["sort_order"]=="updateDate desc"
            summary=weekly_source_summary(db,"federal",today=date.today())
            assert summary["item_count"]==1
            assert summary["categories"][0]["items"][0]["category"]=="education"
            repeat=discover_federal_batch(db,congress=119,batch_size=1)
            assert repeat["weekly_actions_captured"]==0
            assert requested==[0,1]
    finally:
        engine.dispose()
