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

def test_civic_week_filters_process_and_merges_overlapping_records_before_limit(tmp_path):
    engine=build_db(tmp_path)
    try:
        with Session(engine) as db:
            def add_doc(source,title,meeting_date,seen,agenda_items=None,category=None,kind="agenda",metadata=None):
                doc=CivicDocument(
                    source_key=source,jurisdiction="TX-local",governing_body="City of Sachse",
                    document_type=kind,title=title,meeting_date=meeting_date,
                    source_url=f"https://example.test/{source}/{title.replace(' ','-')}",
                    external_id=f"{source}:{title}",text=title,sha256=title,
                    metadata_json=metadata or {},first_seen_at=seen,last_seen_at=seen,
                )
                db.add(doc);db.flush()
                rev=CivicDocumentRevision(civic_document_id=doc.id,sha256=title,
                                          text=title,metadata_json={},observed_at=seen)
                db.add(rev);db.flush()
                for ordinal,(heading,body,signal) in enumerate(agenda_items or [],1):
                    agenda=CivicAgendaItem(civic_document_id=doc.id,revision_id=rev.id,
                        ordinal=ordinal,item_number=str(ordinal),heading=heading,text=body,
                        evidence_hash=f"{title}:{ordinal}",metadata_json={})
                    db.add(agenda);db.flush()
                    if signal:
                        db.add(CivicFinding(civic_document_id=doc.id,revision_id=rev.id,
                            agenda_item_id=agenda.id,category=signal,statement=signal,
                            evidence=body,confidence=1.0,evidence_hash=f"{title}:f{ordinal}",
                            metadata_json={}))
                if category:
                    db.add(CivicFinding(civic_document_id=doc.id,revision_id=rev.id,
                        agenda_item_id=None,category=category,statement=category,
                        evidence=title,confidence=1.0,evidence_hash=f"{title}:doc",metadata_json={}))
                return doc

            seen=datetime(2026,9,22,8)
            shared="Consider approval of the Oak Street sidewalk construction contract for $2 million."
            add_doc("sachse_current_meetings","Council agenda","2026-09-22",seen,[
                ("Call to order","Call to order and establish a quorum.",None),
                ("Approve the minutes","Approve minutes of the previous meeting.","vote_action"),
                ("Approve Oak Street sidewalk construction contract",shared,"procurement_contract"),
                ("Adjournment","Adjourn meeting.",None),
            ])
            add_doc("sachse_council_agendas","Council packet","2026-09-22",seen,[
                ("Consider approval of the Oak Street sidewalk construction contract",shared,"vote_action"),
                ("Adopt the neighborhood parking ordinance",
                 "Consider adoption of the neighborhood parking ordinance.","policy_rule"),
            ])
            add_doc("sachse_council_minutes","Regular Council Meeting - Minutes",
                    "2026-09-22",seen,category="procurement_contract",kind="minutes")
            add_doc("sachse_development_reports","Development services home",None,
                    seen,category="zoning_development",kind="web_record")
            add_doc("sachse_council_agendas","Council index", "2026-09-22",seen,
                    [("Approve unrelated contract from a navigation link",
                      "Consider approval of a contract linked from the index.","procurement_contract")],
                    metadata={"crawl_depth":0})
            db.commit()
            result=weekly_source_summary(db,"sachse",limit=2,today=date(2026,9,23))

        titles=[item["title"] for category in result["categories"] for item in category["items"]]
        assert result["item_count"]==2
        assert "Adopt the neighborhood parking ordinance" in titles
        assert sum("Oak Street sidewalk construction contract" in title for title in titles)==1
    finally:
        engine.dispose()

def test_legislative_week_ignores_admin_action_but_keeps_substantive_action(tmp_path):
    engine=build_db(tmp_path)
    try:
        with Session(engine) as db:
            bill=Bill(jurisdiction="US",congress=119,session_code="119",bill_type="hr",
                      bill_number="42",title="School funding",metadata_json={},
                      updated_at=datetime(2026,9,23,9))
            db.add(bill);db.flush()
            for day,text in [(22,"Referred to the Committee on Education."),
                             (23,"Cosponsors added to the bill.")]:
                db.add(BillAction(bill_id=bill.id,action_date=f"2026-09-{day}",
                                  text=text,source_url="https://example.test/bill",
                                  raw_json={}))
            db.commit()
            result=weekly_source_summary(db,"federal",today=date(2026,9,23))
        assert result["item_count"]==1
        item=result["categories"][0]["items"][0]
        assert item["date"]=="2026-09-22"
        assert item["action_count_this_week"]==1
    finally:
        engine.dispose()

def test_sachse_legacy_agenda_shows_issues_under_sections_without_contact_or_procedure(tmp_path):
    engine=build_db(tmp_path)
    try:
        with Session(engine) as db:
            source_text="""3815 Sachse Road, Building B
Sachse Road, Building B
City Hall Phone: 972.495.1212
A. Call to Order
B. Public Comments
C. Consent Agenda
C1. Consider approval of a street repair contract with Acme.
D. Action Resulting from Executive Action
D1. Consider adopting a zoning ordinance for Oak Street.
E. Adjournment"""
            doc=CivicDocument(source_key="sachse_current_meetings",jurisdiction="TX-local",
                governing_body="City of Sachse",document_type="agenda",
                title="City Council Meeting - Agenda",meeting_date="2026-09-22",
                source_url="https://example.test/sachse",external_id="agenda-2026-09-22",
                text=source_text,sha256="sachse",metadata_json={},
                first_seen_at=datetime(2026,9,22),last_seen_at=datetime(2026,9,22))
            db.add(doc);db.flush()
            rev=CivicDocumentRevision(civic_document_id=doc.id,sha256="sachse",
                text=source_text,metadata_json={},observed_at=datetime(2026,9,22))
            db.add(rev);db.flush()
            headings=[
                ("3815","Sachse Road, Building B", "3815 Sachse Road, Building B",None),
                ("3815","Sachse Road", "3815 Sachse Road, Sachse, TX 75048",None),
                ("A","Call to Order", "A. Call to Order",None),
                ("B","Public Comments", "B. Public Comments",None),
                ("C1","Consider approval of a street repair contract with Acme",
                 "Consider approval of a street repair contract with Acme.","procurement_contract"),
                ("D","Action Resulting from Executive Action",
                 "D. Action Resulting from Executive Action",None),
                ("D1","Consider adopting a zoning ordinance for Oak Street",
                 "Consider adopting a zoning ordinance for Oak Street.","zoning_development"),
                ("E","Adjournment", "E. Adjournment",None),
            ]
            for ordinal,(number,heading,body,signal) in enumerate(headings,1):
                item=CivicAgendaItem(civic_document_id=doc.id,revision_id=rev.id,
                    ordinal=ordinal,item_number=number,heading=heading,text=body,
                    evidence_hash=str(ordinal),metadata_json={})
                db.add(item);db.flush()
                if signal:
                    db.add(CivicFinding(civic_document_id=doc.id,revision_id=rev.id,
                        agenda_item_id=item.id,category=signal,statement=signal,
                        evidence=body,confidence=1.0,evidence_hash=f"f{ordinal}",metadata_json={}))
            db.commit()
            result=weekly_source_summary(db,"sachse",today=date(2026,9,23))

        items=[item for group in result["categories"] for item in group["items"]]
        assert result["item_count"]==2
        assert {item["agenda_section"] for item in items}=={
            "Consent Agenda","Action Resulting from Executive Action"}
        assert all("Sachse Road" not in item["title"] for item in items)
    finally:
        engine.dispose()

def test_arcgis_feature_needs_change_this_week_not_just_a_recrawl(tmp_path):
    engine=build_db(tmp_path)
    try:
        with Session(engine) as db:
            for label,observed in [("Old project",datetime(2026,9,1)),
                                   ("Updated project",datetime(2026,9,22))]:
                doc=CivicDocument(source_key="wylie_development_projects",
                    jurisdiction="TX-local",governing_body="City of Wylie",
                    document_type="web_record",title=label,meeting_date=None,
                    source_url="https://example.test/feature",external_id=label,
                    text="Zoning project status updated",sha256=label,
                    metadata_json={"record_type":"arcgis_feature"},
                    first_seen_at=observed,last_seen_at=datetime(2026,9,23))
                db.add(doc);db.flush()
                revision=CivicDocumentRevision(civic_document_id=doc.id,sha256=label,
                    text=doc.text,metadata_json={},observed_at=observed)
                db.add(revision)
                db.flush()
                db.add(CivicFinding(civic_document_id=doc.id,
                    revision_id=revision.id,
                    agenda_item_id=None,category="zoning_development",statement="Project",
                    evidence=doc.text,confidence=1.0,evidence_hash=label,metadata_json={}))
            db.commit()
            result=weekly_source_summary(db,"wylie",today=date(2026,9,23))
        assert result["item_count"]==1
        assert result["categories"][0]["items"][0]["title"]=="Updated project"
    finally:
        engine.dispose()
