from pydantic import BaseModel, Field

class EntityCreate(BaseModel):
    entity_type: str = Field(min_length=1, max_length=32)
    canonical_name: str = Field(min_length=1)
    external_ids: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)

class RelationshipCreate(BaseModel):
    source_entity_id: int
    target_entity_id: int
    relation_type: str = Field(min_length=1, max_length=64)
    evidence: str = Field(min_length=1)
    source_url: str | None = None
    observed_on: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_system: str = Field(default="manual", min_length=1, max_length=64)
    metadata: dict = Field(default_factory=dict)
