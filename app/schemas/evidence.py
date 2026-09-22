from pydantic import BaseModel, Field

class FECCandidateImport(BaseModel):
    person_entity_id: int
    candidate_id: str = Field(min_length=1)
    cycle: int | None = None

class FECReceiptImport(BaseModel):
    committee_entity_id: int
    committee_id: str = Field(min_length=1)
    contributor_name: str = Field(min_length=1)
    min_date: str | None = None
    max_date: str | None = None

class LDAClientImport(BaseModel):
    client_name: str = Field(min_length=1)
    filing_year: int | None = None
    max_records: int = Field(default=100, ge=1, le=1000)
