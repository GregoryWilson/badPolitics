import pytest
from pydantic import ValidationError
from app.schemas.evidence import FECCandidateImport, FECReceiptImport, LDAClientImport

def test_fec_candidate_import_requires_explicit_candidate_id():
    p=FECCandidateImport(person_entity_id=1,candidate_id="H0TX00000",cycle=2026)
    assert p.person_entity_id == 1
    assert p.candidate_id == "H0TX00000"

def test_fec_receipt_import_requires_contributor_name():
    with pytest.raises(ValidationError):
        FECReceiptImport(committee_entity_id=2,committee_id="C00000000",contributor_name="")

def test_lda_import_bounds_record_count():
    with pytest.raises(ValidationError):
        LDAClientImport(client_name="Example Corp",max_records=1001)
