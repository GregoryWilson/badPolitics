from pydantic import BaseModel, Field, model_validator

QUEUE_STATUSES={"new","reviewing","needs_evidence","completed","archived","superseded"}

class QueueItemUpdate(BaseModel):
    status: str | None = None
    analyst_notes: str | None = Field(default=None,max_length=20000)

    @model_validator(mode="after")
    def validate_status(self):
        if self.status is not None and self.status not in QUEUE_STATUSES-{"superseded"}:
            raise ValueError("status must be new, reviewing, needs_evidence, completed, or archived")
        return self
