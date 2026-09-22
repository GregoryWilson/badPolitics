from dataclasses import dataclass, field
from typing import Protocol

@dataclass
class NormalizedVersion:
    code: str
    name: str | None
    source_url: str
    issued_on: str | None = None
    text: str | None = None
    format: str = "html"

@dataclass
class NormalizedAction:
    date: str | None
    text: str
    code: str | None = None
    source_url: str | None = None
    raw: dict = field(default_factory=dict)

@dataclass
class NormalizedSponsor:
    name: str
    role: str
    external_id: str | None = None
    party: str | None = None
    district: str | None = None
    raw: dict = field(default_factory=dict)

@dataclass
class NormalizedAmendment:
    amendment_type: str
    amendment_number: str
    description: str | None = None
    latest_action: str | None = None
    source_url: str | None = None
    raw: dict = field(default_factory=dict)

@dataclass
class NormalizedBill:
    jurisdiction: str
    session: str
    session_number: int
    bill_type: str
    bill_number: str
    title: str | None
    latest_action: str | None
    source_url: str
    source_system: str
    metadata: dict = field(default_factory=dict)
    versions: list[NormalizedVersion] = field(default_factory=list)
    actions: list[NormalizedAction] = field(default_factory=list)
    sponsors: list[NormalizedSponsor] = field(default_factory=list)
    amendments: list[NormalizedAmendment] = field(default_factory=list)

class JurisdictionAdapter(Protocol):
    code: str
    name: str
    source_system: str

    def fetch_bill(self, session:str, bill_type:str, number:str) -> NormalizedBill:
        ...

    def source_info(self) -> dict:
        ...
