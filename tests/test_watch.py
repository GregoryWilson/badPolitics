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
    assert _bill_key(119,"HR","123")=="119:hr:123"
