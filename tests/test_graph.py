from app.services.graph import normalize_name, BENEFICIARY_PATTERNS, GEO_PATTERN

def test_normalize_name():
    assert normalize_name("  North   Plains DISTRICT ") == "north plains district"

def test_beneficiary_detection():
    text = "Grants may be awarded to nonprofit organizations and small businesses."
    matches = [p.search(text) for p in BENEFICIARY_PATTERNS]
    assert sum(bool(m) for m in matches) >= 2

def test_named_geography_detection():
    assert GEO_PATTERN.search("The pilot applies within North Plains Groundwater Conservation District.")
    assert GEO_PATTERN.search("Funds may be used by the City of Wylie for eligible activities.")
