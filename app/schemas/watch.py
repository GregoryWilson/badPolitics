from pydantic import BaseModel, Field, model_validator

class WatchCreate(BaseModel):
    name: str = Field(min_length=1)
    target_type: str
    jurisdiction: str = "US"
    congress: int | None = None
    bill_type: str | None = None
    bill_number: str | None = None
    auto_research: bool = False
    auto_report: bool = False
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_target(self):
        self.jurisdiction=self.jurisdiction.upper()
        if self.target_type not in {"bill","congress","session"}:
            raise ValueError("target_type must be bill, congress, or session")
        if self.target_type=="congress" and self.jurisdiction!="US":
            raise ValueError("congress watches currently apply only to US federal legislation")
        if self.target_type=="session" and self.jurisdiction=="US":
            raise ValueError("US federal monitoring uses congress watches")
        if self.target_type=="bill" and not (self.congress and self.bill_type and self.bill_number):
            raise ValueError("bill watches require congress, bill_type, and bill_number")
        if self.target_type=="congress" and not self.congress:
            raise ValueError("congress watches require congress")
        if self.target_type=="session" and not (self.congress and self.metadata.get("session")):
            raise ValueError("session watches require congress/session number and metadata.session")
        return self

class WatchUpdate(BaseModel):
    active: bool | None = None
    auto_research: bool | None = None
    auto_report: bool | None = None
