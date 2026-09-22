from app.services.monitor import BILL_TYPES

def test_bill_type_mapping():
    assert BILL_TYPES["HR"]=="hr"
    assert BILL_TYPES["S"]=="s"
