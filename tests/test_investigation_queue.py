from types import SimpleNamespace
import pytest
from pydantic import ValidationError

from app.schemas.queue import QueueItemUpdate
from app.services.investigation_queue import _trigger_types, _coverage, _gaps
import app.services.watch as watch_service

def packet():
    return {
        "evidence":[
            {
                "evidence_id":"S1",
                "kind":"section_text",
                "source_url":"https://example.test/bill",
                "metadata":{},
            },
            {
                "evidence_id":"Q1",
                "kind":"scope_finding",
                "source_url":"https://example.test/bill",
                "metadata":{"category":"late_scope_outlier"},
            },
            {
                "evidence_id":"L1",
                "kind":"provision_lineage",
                "source_url":"https://example.test/v2",
                "metadata":{"event_type":"introduced"},
            },
            {
                "evidence_id":"A1",
                "kind":"candidate_amendment",
                "source_url":"https://example.test/amendment",
                "metadata":{},
            },
            {
                "evidence_id":"E1",
                "kind":"named_organization",
                "source_url":"https://example.test/bill",
                "metadata":{},
            },
            {
                "evidence_id":"C1",
                "kind":"external_correlation",
                "source_url":None,
                "metadata":{},
            },
            {
                "evidence_id":"X1",
                "kind":"external_relationship",
                "source_url":"https://example.test/external",
                "metadata":{},
            },
            {
                "evidence_id":"F1",
                "kind":"bill_level_fiscal_context",
                "source_url":"https://example.test/fiscal",
                "metadata":{"category":"implementation_cost"},
            },
            {
                "evidence_id":"D1",
                "kind":"deterministic_finding",
                "source_url":"https://example.test/bill",
                "metadata":{"kind":"exemption"},
            },
        ]
    }

def test_queue_trigger_types_are_descriptive():
    triggers=_trigger_types(packet())
    assert triggers==sorted([
        "bill_text_exemption",
        "candidate_amendment",
        "external_correlation",
        "external_relationship",
        "fiscal_implementation_cost",
        "late_scope_outlier",
        "lineage_introduced",
        "named_organization",
    ])

def test_queue_coverage_tracks_sources_without_quality_score():
    coverage=_coverage(packet(),narrative="Summary [S1].")
    assert coverage["entry_count"]==9
    assert coverage["has_scope_analysis"] is True
    assert coverage["has_lineage"] is True
    assert coverage["has_external_context"] is True
    assert coverage["has_fiscal_context"] is True
    assert coverage["has_local_synthesis"] is True
    assert "score" not in coverage

def test_queue_gap_detection_only_reports_missing_provenance():
    sample=packet()
    assert _gaps(sample)==[]
    sample["evidence"][3]["source_url"]=None
    sample["evidence"][6]["source_url"]=None
    assert _gaps(sample)==[
        "candidate_amendment_source_url",
        "external_relationship_source_url",
    ]

def test_queue_update_rejects_non_workflow_labels():
    with pytest.raises(ValidationError):
        QueueItemUpdate(status="high_risk")

def test_watch_queue_failure_is_non_blocking(monkeypatch):
    def fail_queue(*args,**kwargs):
        raise RuntimeError("queue unavailable")
    monkeypatch.setattr(watch_service,"sync_bill_queue",fail_queue)
    result=watch_service._refresh_outputs(
        db=object(),
        watch=SimpleNamespace(auto_research=False,auto_report=False),
        bill=SimpleNamespace(id=12),
        events=[SimpleNamespace(id=1)],
    )
    assert result["queue_error"]=="queue unavailable"
