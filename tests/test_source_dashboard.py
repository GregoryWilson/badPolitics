from datetime import date,datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
import app.models.entities  # noqa: F401
from app.models.entities import (
    Bill,BillAction,CivicDocument,CivicDocumentRevision,CivicAgendaItem,CivicFinding,
)
from app.services.source_dashboard import dashboard_sources,weekly_source_summary

def build_db(tmp_path):
    engine=create_engine("sqlite:///"+str(tmp_path/"weekly.db"))
    Base.metadata.create_all(engine)
    return engine

def test_dashboard_source_catalog_groups_institutions():
    ids={row["id"] for row in dashboard_sources()}
    assert {"sachse","wylie","wylie_isd","gisd","dallas_county","collin_county","texas","federal"} <= ids

def test_gisd_weekly_summary_breaks_agenda_into_logical_items(tmp_path):
    engine=build_db(tmp_path)
    try:
        with Session(engine) as db:
            doc=CivicDocument(
                source_key="gisd_board",jurisdiction="TX-local",
                governing_body="Garland ISD Board of Trustees",
                document_type="agenda",title="Regular Board Meeting",
                meeting_date="2026-09-22",source_url="https://example.test/gisd",
                external_id="gisd-week",text="agenda",sha256="doc",
                metadata_json={},first_seen_at=datetime(2026,9,22,8),
                last_seen_at=datetime(2026,9,22,8),
            )
            db.add(doc); db.flush()
            rev=CivicDocumentRevision(
                civic_document_id=doc.id,sha256="rev",text="agenda",
                metadata_json={},observed_at=datetime(2026,9,22,8),
            )
            db.add(rev); db.flush()
            contract=CivicAgendaItem(
                civic_document_id=doc.id,revision_id=rev.id,ordinal=1,item_number="1",
                heading="Approve construction contract",text="Consider approval of a $2,500,000 construction contract.",
                evidence_hash="a",metadata_json={},
            )
            policy=CivicAgendaItem(
                civic_document_id=doc.id,revision_id=rev.id,ordinal=2,item_number="2",
                heading="Adopt student device policy",text="Consider adoption of the revised student device policy.",
                evidence_hash="b",metadata_json={},
            )
            db.add_all([contract,policy]); db.flush()
            db.add_all([
                CivicFinding(
                    civic_document_id=doc.id,revision_id=rev.id,agenda_item_id=contract.id,
                    category="procurement_contract",statement="Contract signal",evidence="construction contract",
                    confidence=1.0,evidence_hash="f1",metadata_json={},
                ),
                CivicFinding(
                    civic_document_id=doc.id,revision_id=rev.id,agenda_item_id=policy.id,
                    category="policy_rule",statement="Policy signal",evidence="student device policy",
                    confidence=1.0,evidence_hash="f2",metadata_json={},
                ),
            ])
            db.commit()
            result=weekly_source_summary(db,"gisd",today=date(2026,9,23))

        assert result["window"]=={"start":"2026-09-21","end":"2026-09-27","label":"This week"}
        assert result["item_count"]==2
        categories={row["category"]:row for row in result["categories"]}
        assert categories["procurement_contract"]["items"][0]["title"]=="Approve construction contract"
        assert categories["policy_rule"]["items"][0]["title"]=="Adopt student device policy"
        assert all(item["source_url"]=="https://example.test/gisd" for row in result["categories"] for item in row["items"])
    finally:
        engine.dispose()

def test_texas_weekly_summary_uses_dated_actions_and_topic_categories(tmp_path):
    engine=build_db(tmp_path)
    try:
        with Session(engine) as db:
            bill=Bill(
                jurisdiction="TX",congress=89,session_code="89S2",
                bill_type="hb",bill_number="10",
                title="Relating to public school finance and teacher compensation",
                latest_action="Referred to committee",metadata_json={},
                updated_at=datetime(2026,9,23,9),
            )
            db.add(bill); db.flush()
            db.add(BillAction(
                bill_id=bill.id,action_date="2026-09-23",
                text="Referred to the Committee on Public Education.",
                action_code=None,source_url="https://example.test/tx/hb10",raw_json={},
            ))
            old=Bill(
                jurisdiction="TX",congress=89,session_code="89R",
                bill_type="hb",bill_number="20",
                title="Relating to highways",latest_action="Passed",
                metadata_json={},updated_at=datetime(2026,9,1),
            )
            db.add(old); db.flush()
            db.add(BillAction(
                bill_id=old.id,action_date="2026-08-30",
                text="Passed.",action_code=None,source_url="https://example.test/old",raw_json={},
            ))
            db.commit()
            result=weekly_source_summary(db,"texas",today=date(2026,9,23))

        assert result["item_count"]==1
        item=result["categories"][0]["items"][0]
        assert item["record_id"]==bill.id
        assert item["category"]=="education"
        assert item["session"]=="89S2"
        assert item["status"]=="referred"
        assert item["source_url"]=="https://example.test/tx/hb10"
    finally:
        engine.dispose()
