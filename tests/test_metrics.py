from app.services.metrics import parse_money_text

def test_parse_money_text():
    assert parse_money_text("$50 million") == 50_000_000
    assert parse_money_text("$1.5 billion") == 1_500_000_000
    assert parse_money_text("$250,000") == 250_000
    assert parse_money_text("no amount") is None
