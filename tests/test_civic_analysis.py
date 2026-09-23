from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
import app.models.entities  # noqa: F401
from app.models.entities import CivicDocument,CivicDocumentRevision
from app.services.civic_analysis import analyze_civic_document,_extract_items,agenda_section_label

def test_agenda_parser_does_not_treat_city_hall_address_as_an_item():
    rows=_extract_items("""3815 Sachse Road, Building B
Sachse, TX 75048
Phone: 972.495.1212
C. Consent Agenda
C1. Consider approval of a street repair contract with Acme.
D. Action Resulting from Executive Action
D1. Consider adopting a zoning ordinance for Oak Street.
1 Consider approval of the capital improvement plan.
""")
    assert [item["item_number"] for item in rows]==["C","C1","D","D1","1"]
    assert agenda_section_label(rows[0]["item_number"],rows[0]["heading"])=="Consent Agenda"
    assert agenda_section_label(rows[2]["item_number"],rows[2]["heading"])=="Action Resulting from Executive Action"

def build_db(tmp_path):
    engine=create_engine("sqlite:///"+str(tmp_path/"civic.db"))
    Base.metadata.create_all(engine)
    return engine

def test_civic_analysis_extracts_structured_review_signals(tmp_path):
    engine=build_db(tmp_path)
    try:
        with Session(engine) as db:
            doc=CivicDocument(
                source_key="gisd_board",
                jurisdiction="TX-local",
                governing_body="Garland ISD Board of Trustees",
                document_type="agenda",
                title="Regular Board Meeting Agenda",
                meeting_date="2026-09-22",
                source_url="https://example.test/agenda",
                external_id="agenda-1",
                text="",
                sha256="abc",
                metadata_json={},
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
            )
            db.add(doc); db.flush()
            text="""1. Consider approval of a $2,500,000 contract with Acme Development LLC for campus renovation.
2. Public Hearing regarding attendance boundary changes.
3. Consider adoption of district policy revisions."""
            rev=CivicDocumentRevision(
                civic_document_id=doc.id,sha256="rev1",text=text,
                metadata_json={},observed_at=datetime.utcnow(),
            )
            db.add(rev); db.commit()
            result=analyze_civic_document(db,doc.id)

        categories={row["category"] for row in result["findings"]}
        assert "procurement_contract" in categories
        assert "school_facility_boundary" in categories
        assert "public_hearing" in categories
        assert "policy_rule" in categories
        assert "explicit_money_mentions" in categories
        assert len(result["agenda_items"])==3
        assert any(e["name"]=="Acme Development LLC" for e in result["entities"])
        money=next(row for row in result["findings"] if row["category"]=="explicit_money_mentions")
        assert money["metadata"]["mention_count"]==1
        assert "$2,500,000" in money["evidence"]
    finally:
        engine.dispose()

def test_civic_analysis_preserves_revision_change_as_separate_signal(tmp_path):
    engine=build_db(tmp_path)
    try:
        with Session(engine) as db:
            doc=CivicDocument(
                source_key="sachse_civic_archive",
                jurisdiction="TX-local",
                governing_body="City of Sachse",
                document_type="agenda",
                title="City Council Agenda",
                meeting_date="2026-09-21",
                source_url="https://example.test/sachse",
                external_id="sachse-1",
                text="",
                sha256="latest",
                metadata_json={},
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
            )
            db.add(doc); db.flush()
            db.add(CivicDocumentRevision(
                civic_document_id=doc.id,sha256="old",text="1. Discuss zoning case Z-1.",
                metadata_json={},observed_at=datetime(2026,9,20,10,0),
            ))
            db.add(CivicDocumentRevision(
                civic_document_id=doc.id,sha256="new",text="1. Consider approval of zoning case Z-1.",
                metadata_json={},observed_at=datetime(2026,9,21,10,0),
            ))
            db.commit()
            result=analyze_civic_document(db,doc.id)

        revisions=[row for row in result["findings"] if row["category"]=="document_revision_change"]
        assert len(revisions)==1
        assert revisions[0]["metadata"]["previous_revision_id"] is not None
        assert "zoning_development" in {row["category"] for row in result["findings"]}
        assert "do not establish" in result["interpretation_note"].lower()
    finally:
        engine.dispose()
