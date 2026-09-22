import pytest
from pydantic import ValidationError
from app.schemas.watch import WatchCreate
from app.services.watch import _bill_key

def test_bill_watch_requires_identity():
    with pytest.raises(ValidationError):
        WatchCreate(name="Incomplete",target_type="bill",congress=119)

def test_congress_watch_requires_congress():
    with pytest.raises(ValidationError):
        WatchCreate(name="Missing Congress",target_type="congress")

def test_bill_watch_normal_shape():
    watch=WatchCreate(
        name="HR 123",
        target_type="bill",
        congress=119,
        bill_type="hr",
        bill_number="123",
    )
    assert watch.congress==119
    assert watch.bill_type=="hr"
    assert watch.bill_number=="123"

def test_bill_key_is_stable():
    assert _bill_key(119,"HR","123")=="US:119:hr:123"


def test_texas_bill_watch_preserves_jurisdiction():
    watch=WatchCreate(
        name="TX HB 9",
        target_type="bill",
        jurisdiction="tx",
        congress=89,
        bill_type="hb",
        bill_number="9",
        metadata={"session":"89R"},
    )
    assert watch.jurisdiction=="TX"
    assert watch.metadata["session"]=="89R"

def test_non_us_congress_watch_is_rejected():
    with pytest.raises(ValidationError):
        WatchCreate(name="TX session",target_type="congress",jurisdiction="TX",congress=89)


def test_texas_session_watch_requires_session_label():
    with pytest.raises(ValidationError):
        WatchCreate(name="TX 89",target_type="session",jurisdiction="TX",congress=89)

def test_texas_session_watch_shape():
    watch=WatchCreate(
        name="Texas 89R",
        target_type="session",
        jurisdiction="TX",
        congress=89,
        metadata={"session":"89R","limit":100},
    )
    assert watch.target_type=="session"
    assert watch.jurisdiction=="TX"
    assert watch.metadata["session"]=="89R"
