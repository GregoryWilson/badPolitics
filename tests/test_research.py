import pytest
from pydantic import ValidationError
from app.schemas.research import ResearchRunRequest

def test_research_defaults_are_bounded():
    req=ResearchRunRequest()
    assert req.max_lda_records_per_entity == 50
    assert req.include_fec_candidate_links is True
    assert req.include_lda_clients is True

def test_research_rejects_unbounded_lda_requests():
    with pytest.raises(ValidationError):
        ResearchRunRequest(max_lda_records_per_entity=251)

def test_research_can_disable_sources():
    req=ResearchRunRequest(include_fec_candidate_links=False,include_lda_clients=False)
    assert req.include_fec_candidate_links is False
    assert req.include_lda_clients is False
