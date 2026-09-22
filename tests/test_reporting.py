from app.services.reporting import _source, FINDING_LABELS

def test_source_shape_preserves_provenance():
    s=_source("bill_finding",12,"https://example.test",{"section":"42"})
    assert s["type"]=="bill_finding"
    assert s["id"]==12
    assert s["url"]=="https://example.test"
    assert s["detail"]["section"]=="42"

def test_core_review_categories_have_neutral_labels():
    assert FINDING_LABELS["money"]=="Explicit monetary amount"
    assert "corrupt" not in " ".join(FINDING_LABELS.values()).lower()
