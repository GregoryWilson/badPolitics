from app.services.graph import ORG_PATTERN

def test_extracts_named_organizations_with_legal_suffixes():
    text="The Secretary shall consult Acme Manufacturing Corporation and North Texas Builders Association."
    matches=[m.group(1) for m in ORG_PATTERN.finditer(text)]
    assert "Acme Manufacturing Corporation" in matches
    assert "North Texas Builders Association" in matches

def test_does_not_extract_generic_beneficiary_class():
    assert ORG_PATTERN.search("Eligible manufacturers may apply for grants.") is None
