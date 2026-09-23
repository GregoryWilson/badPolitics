from datetime import datetime, date

import httpx

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
import app.models.entities  # noqa: F401
from app.models.entities import CivicDocument, CivicDocumentRevision, DiscoveryCursor
from app.services.auto_discovery import list_civic_documents, discovery_status
from app.services.civic_analysis import ensure_civic_analysis, ANALYZER_VERSION
from app.services.civic_crawler import _extract_date, _doc_type, _arcgis_text, scan_civic_source
from app.services.civic_sources import CIVIC_SOURCES
from app.services.source_dashboard import weekly_source_summary

def test_gisd_sources_are_first_class_and_high_priority():
    sources={row["source_key"]:row for row in CIVIC_SOURCES}
    assert sources["gisd_board"]["priority"]=="high"
    assert sources["gisd_board"]["kind"]=="boardbook"
    assert sources["gisd_board"]["organization_id"]=="1084"
    assert sources["gisd_bond"]["priority"]=="high"
    assert sources["gisd_consolidation"]["priority"]=="high"
    assert sources["gisd_policies"]["priority"]=="high"

def test_wylie_and_county_sources_are_registered():
    sources={row["source_key"]:row for row in CIVIC_SOURCES}
    assert sources["wylie_isd_board"]["kind"]=="boardbook"
    assert sources["wylie_isd_board"]["organization_id"]=="3480"
    assert "wylie_development_projects" in sources
    assert "collin_commissioners" in sources
    assert sources["collin_commissioners"]["kind"]=="collin_eagenda"
    assert "dallas_commissioners_notices" in sources

def test_collin_eagenda_yields_dated_agenda_items(tmp_path,monkeypatch):
    meeting=date.today()
    index=f'''<a title="View Agenda for Commissioners Court ({meeting:%m/%d/%Y})"
        href="agenda_publish.cfm?dsp=ag&amp;seq=3277">{meeting:%B %d, %Y}</a>'''
    agenda='''<a class="ai_link" href="agenda_item.cfm?id=1">Consider approving an agreement for road construction</a>
              <a class="ai_link" href="agenda_item.cfm?id=2">Call to Order</a>'''
    def handle(request):
        return httpx.Response(200,text=agenda if request.url.params.get("seq")=="3277" else index)
    original_client=httpx.Client
    monkeypatch.setattr("app.services.civic_crawler.httpx.Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handle),**kwargs))
    engine=_db(tmp_path)
    try:
        with Session(engine) as db:
            result=scan_civic_source(db,"collin_commissioners",limit=10)
            assert result["error_count"]==0
            assert result["document_count"]==1
            doc=db.get(CivicDocument,result["changed_document_ids"][0])
            assert doc.meeting_date==meeting.isoformat()
            assert doc.source_url.endswith("seq=3277")
            ensure_civic_analysis(db,doc.id)
            summary=weekly_source_summary(db,"collin_county",today=meeting)
            items=[item for group in summary["categories"] for item in group["items"]]
            assert len(items)==1
            assert "road construction" in items[0]["title"]
            assert items[0]["source_url"]==doc.source_url
    finally:
        engine.dispose()

def test_sachse_current_and_historical_sources_are_registered():
    sources={row["source_key"]:row for row in CIVIC_SOURCES}
    assert sources["sachse_current_meetings"]["kind"]=="civicclerk"
    assert sources["sachse_current_meetings"]["tenant"]=="sachsetx"
    assert sources["sachse_council_agendas"]["kind"]=="civicengage_archive"
    assert sources["sachse_council_minutes"]["kind"]=="civicengage_archive"
    assert sources["sachse_pz_agendas"]["kind"]=="civicengage_archive"
    assert sources["sachse_development_reports"]["kind"]=="civicengage_archive"

def test_dallas_county_sources_are_registered_and_high_priority():
    sources={row["source_key"]:row for row in CIVIC_SOURCES}
    assert sources["dallas_commissioners_notices"]["priority"]=="high"
    assert sources["dallas_commissioners_notices"]["kind"]=="dallas_notices"
    assert sources["dallas_budget"]["priority"]=="high"

def test_civic_date_extraction_handles_meeting_formats():
    assert _extract_date("Regular meeting September 22, 2026")=="2026-09-22"
    assert _extract_date("Meeting 09/08/2026")=="2026-09-08"
    assert _extract_date("2026-10-06 agenda")=="2026-10-06"

def test_civic_document_type_classification():
    assert _doc_type("Board Meeting Minutes","https://example.test/doc")=="minutes"
    assert _doc_type("Finance Committee Agenda","https://example.test/doc")=="agenda"
    assert _doc_type("Zoning Case","https://example.test/doc")=="zoning"
    assert _doc_type("Bond Special Meeting","https://example.test/doc")=="bond"

def test_arcgis_text_suppresses_null_and_technical_fields():
    text=_arcgis_text({
        "OBJECTID":42,
        "GlobalID":"guid",
        "PlanZoningCase":"ZC 2026-12",
        "ProjectName":"Example Mixed Use",
        "ExistingZoning":"AG",
        "RequestedZoning":"PD",
        "CouncilStatus":"Approved",
        "OrdinanceNumber":"2026-31",
        "Description":None,
        "Notes":"",
    })
    assert "Example Mixed Use" in text
    assert "Existing Zoning: AG" in text
    assert "Requested Zoning: PD" in text
    assert "Council Status: Approved" in text
    assert "Ordinance Number: 2026-31" in text
    assert "OBJECTID" not in text
    assert "GlobalID" not in text
    assert "None" not in text
    assert "null" not in text.casefold()

def _db(tmp_path):
    engine=create_engine("sqlite:///"+str(tmp_path/"civic-discovery.db"))
    Base.metadata.create_all(engine)
    return engine

def test_analysis_get_path_analyzes_unprocessed_revision(tmp_path):
    engine=_db(tmp_path)
    try:
        with Session(engine) as db:
            doc=CivicDocument(
                source_key="wylie_development_projects",
                jurisdiction="TX-local",
                governing_body="City of Wylie Planning & Zoning / City Council",
                document_type="zoning",
                title="ZC 2026-12",
                meeting_date="2026-09-01",
                source_url="https://example.test/wylie",
                external_id="wylie-1",
                text="Requested Zoning: PD\nCouncil Status: Approved",
                sha256="doc",
                metadata_json={},
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
            )
            db.add(doc); db.flush()
            revision=CivicDocumentRevision(
                civic_document_id=doc.id,
                sha256="rev",
                text=doc.text,
                metadata_json={},
                observed_at=datetime.utcnow(),
            )
            db.add(revision); db.commit()
            result=ensure_civic_analysis(db,doc.id)
            db.refresh(revision)
            assert result["analysis_ready"] is True
            assert revision.metadata_json["civic_analysis_version"]==ANALYZER_VERSION
            assert "zoning_development" in {x["category"] for x in result["findings"]}
    finally:
        engine.dispose()

def test_civic_list_round_robins_across_sources(tmp_path):
    engine=_db(tmp_path)
    try:
        with Session(engine) as db:
            now=datetime.utcnow()
            for i in range(10):
                db.add(CivicDocument(
                    source_key="wylie_development_projects",
                    jurisdiction="TX-local",governing_body="Wylie",
                    document_type="zoning",title=f"Wylie {i}",
                    meeting_date=f"2026-09-{20-i:02d}",
                    source_url=f"https://example.test/w/{i}",external_id=f"w{i}",
                    text="x",sha256=f"w{i}",metadata_json={},
                    first_seen_at=now,last_seen_at=now,
                ))
            for source,title in (
                ("gisd_board","GISD Agenda"),
                ("sachse_current_meetings","Sachse Agenda"),
                ("dallas_commissioners_notices","Dallas Agenda"),
            ):
                db.add(CivicDocument(
                    source_key=source,jurisdiction="TX-local",
                    governing_body=source,document_type="agenda",title=title,
                    meeting_date="2026-09-19",source_url=f"https://example.test/{source}",
                    external_id=source,text="x",sha256=source,metadata_json={},
                    first_seen_at=now,last_seen_at=now,
                ))
            db.commit()
            rows=list_civic_documents(db,limit=8)
            keys={row["source_key"] for row in rows}
            assert {"wylie_development_projects","gisd_board","sachse_current_meetings","dallas_commissioners_notices"} <= keys
    finally:
        engine.dispose()


def test_discovery_status_hides_retired_sources_by_default(tmp_path):
    engine=_db(tmp_path)
    try:
        with Session(engine) as db:
            db.add(DiscoveryCursor(
                source_key="civic:sachse_civic_archive",
                jurisdiction="TX-local",
                session=None,
                cursor_json={"offset":0},
                cycle=3,
                status="idle",
                updated_at=datetime.utcnow(),
            ))
            db.add(DiscoveryCursor(
                source_key="civic:gisd_board",
                jurisdiction="TX-local",
                session=None,
                cursor_json={"offset":0},
                cycle=3,
                status="idle",
                updated_at=datetime.utcnow(),
            ))
            db.commit()
            active={row["source_key"] for row in discovery_status(db)}
            all_rows={row["source_key"] for row in discovery_status(db,include_inactive=True)}
            assert "civic:gisd_board" in active
            assert "civic:sachse_civic_archive" not in active
            assert "civic:sachse_civic_archive" in all_rows
    finally:
        engine.dispose()
