from types import SimpleNamespace
from app.services.correlation import _match

def entity(name,external_ids=None,aliases=None):
    return SimpleNamespace(
        id=1,
        normalized_name=" ".join(name.casefold().split()),
        canonical_name=name,
        external_ids=external_ids or {},
        metadata_json={"aliases":aliases or []},
        entity_type="organization",
    )

def test_external_id_match_is_strongest():
    a=entity("Alpha",{"fec_committee_id":"C123"})
    b=entity("Different Name",{"fec_committee_id":"C123"})
    basis,confidence,_=_match(a,b)
    assert basis=="external_id"
    assert confidence==1.0

def test_exact_name_match():
    a=entity("Acme Corporation")
    b=entity("  ACME   CORPORATION ")
    basis,confidence,_=_match(a,b)
    assert basis=="exact_name"
    assert confidence==0.95

def test_explicit_alias_match():
    a=entity("Acme Corp",aliases=["Acme Incorporated"])
    b=entity("Acme Incorporated")
    basis,confidence,_=_match(a,b)
    assert basis=="alias"
    assert confidence==0.85

def test_no_fuzzy_match():
    a=entity("Acme Corporation")
    b=entity("Acme Holdings")
    assert _match(a,b) is None


def test_name_match_rejects_incompatible_types():
    a=entity("Jordan Smith")
    a.entity_type="person"
    b=entity("Jordan Smith")
    b.entity_type="organization"
    assert _match(a,b) is None


def test_external_id_can_match_across_entity_subtypes():
    a=entity("Candidate Committee",{"fec_committee_id":"C999"})
    a.entity_type="committee"
    b=entity("Committee Alias",{"fec_committee_id":"C999"})
    b.entity_type="organization"
    basis,confidence,_=_match(a,b)
    assert basis=="external_id"
    assert confidence==1.0
