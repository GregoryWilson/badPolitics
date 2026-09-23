from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
import app.models.entities  # noqa: F401
from app.models.entities import CivicDocument, CivicDocumentRevision
from app.services.auto_discovery import list_civic_documents
from app.services.civic_analysis import ensure_civic_analysis, ANALYZER_VERSION
from app.services.civic_crawler import _extract_date, _doc_type, _arcgis_text
from app.services.civic_sources import CIVIC_SOURCES

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
    assert "dallas_commissioners_notices" in sources

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
                text="RequestedZoning: PD\nCouncilStatus: Approved",
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
