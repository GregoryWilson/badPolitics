from app.services.civic_crawler import _extract_date, _doc_type
from app.services.civic_sources import CIVIC_SOURCES

def test_gisd_sources_are_first_class_and_high_priority():
    sources={row["source_key"]:row for row in CIVIC_SOURCES}
    assert sources["gisd_board"]["priority"]=="high"
    assert sources["gisd_bond"]["priority"]=="high"
    assert sources["gisd_consolidation"]["priority"]=="high"
    assert sources["gisd_policies"]["priority"]=="high"
    assert "meetings.boardbook.org" in sources["gisd_board"]["allow_domains"]

def test_wylie_and_county_sources_are_registered():
    keys={row["source_key"] for row in CIVIC_SOURCES}
    assert {"wylie_isd_board","wylie_development_projects","collin_commissioners"} <= keys

def test_civic_date_extraction_handles_meeting_formats():
    assert _extract_date("Regular meeting September 22, 2026")=="2026-09-22"
    assert _extract_date("Meeting 09/08/2026")=="2026-09-08"
    assert _extract_date("2026-10-06 agenda")=="2026-10-06"

def test_civic_document_type_classification():
    assert _doc_type("Board Meeting Minutes","https://example.test/doc")=="minutes"
    assert _doc_type("Finance Committee Agenda","https://example.test/doc")=="agenda"
    assert _doc_type("Zoning Case","https://example.test/doc")=="zoning"
    assert _doc_type("Bond Special Meeting","https://example.test/doc")=="bond"
