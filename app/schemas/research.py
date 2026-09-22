from pydantic import BaseModel, Field

class ResearchRunRequest(BaseModel):
    filing_year: int | None = None
    max_lda_records_per_entity: int = Field(default=50, ge=1, le=250)
    include_fec_candidate_links: bool = True
    include_lda_clients: bool = True
