from pydantic import BaseModel, Field, model_validator

class WatchCreate(BaseModel):
    name: str = Field(min_length=1)
    target_type: str
    congress: int | None = None
    bill_type: str | None = None
    bill_number: str | None = None
    auto_research: bool = False
    auto_report: bool = False
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_target(self):
        if self.target_type not in {"bill","congress"}:
            raise ValueError("target_type must be bill or congress")
        if self.target_type=="bill" and not (self.congress and self.bill_type and self.bill_number):
            raise ValueError("bill watches require congress, bill_type, and bill_number")
        if self.target_type=="congress" and not self.congress:
            raise ValueError("congress watches require congress")
        return self

class WatchUpdate(BaseModel):
    active: bool | None = None
    auto_research: bool | None = None
    auto_report: bool | None = None
