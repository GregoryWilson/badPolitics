from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, JSON, UniqueConstraint, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class Bill(Base):
    __tablename__="bills"
    id:Mapped[int]=mapped_column(primary_key=True)
    jurisdiction:Mapped[str]=mapped_column(String(32),default="US")
    congress:Mapped[int]=mapped_column(Integer)
    bill_type:Mapped[str]=mapped_column(String(16))
    bill_number:Mapped[str]=mapped_column(String(32))
    title:Mapped[str|None]=mapped_column(Text)
    latest_action:Mapped[str|None]=mapped_column(Text)
    metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
    updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    versions=relationship("BillVersion",back_populates="bill",cascade="all,delete-orphan")
    actions=relationship("BillAction",back_populates="bill",cascade="all,delete-orphan")
    sponsors=relationship("BillSponsor",back_populates="bill",cascade="all,delete-orphan")
    amendments=relationship("Amendment",back_populates="bill",cascade="all,delete-orphan")
    __table_args__=(UniqueConstraint("jurisdiction","congress","bill_type","bill_number"),)

class BillVersion(Base):
    __tablename__="bill_versions"
    id:Mapped[int]=mapped_column(primary_key=True)
    bill_id:Mapped[int]=mapped_column(ForeignKey("bills.id",ondelete="CASCADE"))
    version_code:Mapped[str]=mapped_column(String(64))
    version_name:Mapped[str|None]=mapped_column(Text)
    source_url:Mapped[str|None]=mapped_column(Text)
    source_system:Mapped[str]=mapped_column(String(32),default="congress")
    source_package_id:Mapped[str|None]=mapped_column(String(128),nullable=True)
    issued_on:Mapped[str|None]=mapped_column(String(32))
    text:Mapped[str]=mapped_column(Text)
    sha256:Mapped[str]=mapped_column(String(64))
    bill=relationship("Bill",back_populates="versions")
    sections=relationship("Section",back_populates="version",cascade="all,delete-orphan")
    findings=relationship("Finding",back_populates="version",cascade="all,delete-orphan")
    __table_args__=(UniqueConstraint("bill_id","version_code","sha256"),)

class BillAction(Base):
    __tablename__="bill_actions"
    id:Mapped[int]=mapped_column(primary_key=True)
    bill_id:Mapped[int]=mapped_column(ForeignKey("bills.id",ondelete="CASCADE"))
    action_date:Mapped[str|None]=mapped_column(String(32))
    text:Mapped[str]=mapped_column(Text)
    action_code:Mapped[str|None]=mapped_column(String(64),nullable=True)
    source_url:Mapped[str|None]=mapped_column(Text,nullable=True)
    raw_json:Mapped[dict]=mapped_column(JSON,default=dict)
    bill=relationship("Bill",back_populates="actions")
    __table_args__=(UniqueConstraint("bill_id","action_date","text"),)

class BillSponsor(Base):
    __tablename__="bill_sponsors"
    id:Mapped[int]=mapped_column(primary_key=True)
    bill_id:Mapped[int]=mapped_column(ForeignKey("bills.id",ondelete="CASCADE"))
    bioguide_id:Mapped[str|None]=mapped_column(String(32),nullable=True)
    full_name:Mapped[str]=mapped_column(Text)
    party:Mapped[str|None]=mapped_column(String(16),nullable=True)
    state:Mapped[str|None]=mapped_column(String(8),nullable=True)
    district:Mapped[str|None]=mapped_column(String(16),nullable=True)
    role:Mapped[str]=mapped_column(String(24),default="cosponsor")
    raw_json:Mapped[dict]=mapped_column(JSON,default=dict)
    bill=relationship("Bill",back_populates="sponsors")
    __table_args__=(UniqueConstraint("bill_id","bioguide_id","role"),)

class Amendment(Base):
    __tablename__="amendments"
    id:Mapped[int]=mapped_column(primary_key=True)
    bill_id:Mapped[int]=mapped_column(ForeignKey("bills.id",ondelete="CASCADE"))
    amendment_type:Mapped[str]=mapped_column(String(16))
    amendment_number:Mapped[str]=mapped_column(String(32))
    congress:Mapped[int]=mapped_column(Integer)
    description:Mapped[str|None]=mapped_column(Text,nullable=True)
    latest_action:Mapped[str|None]=mapped_column(Text,nullable=True)
    source_url:Mapped[str|None]=mapped_column(Text,nullable=True)
    raw_json:Mapped[dict]=mapped_column(JSON,default=dict)
    bill=relationship("Bill",back_populates="amendments")
    __table_args__=(UniqueConstraint("congress","amendment_type","amendment_number"),)

class Section(Base):
    __tablename__="sections"
    id:Mapped[int]=mapped_column(primary_key=True)
    version_id:Mapped[int]=mapped_column(ForeignKey("bill_versions.id",ondelete="CASCADE"))
    section_number:Mapped[str]=mapped_column(String(64))
    heading:Mapped[str|None]=mapped_column(Text)
    text:Mapped[str]=mapped_column(Text)
    ordinal:Mapped[int]=mapped_column(Integer)
    version=relationship("BillVersion",back_populates="sections")

class Finding(Base):
    __tablename__="findings"
    id:Mapped[int]=mapped_column(primary_key=True)
    version_id:Mapped[int]=mapped_column(ForeignKey("bill_versions.id",ondelete="CASCADE"))
    section_id:Mapped[int|None]=mapped_column(ForeignKey("sections.id",ondelete="CASCADE"),nullable=True)
    kind:Mapped[str]=mapped_column(String(64))
    severity:Mapped[float]=mapped_column(Float,default=0)
    label:Mapped[str]=mapped_column(Text)
    evidence:Mapped[str]=mapped_column(Text)
    metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
    version=relationship("BillVersion",back_populates="findings")


class EvidenceEntity(Base):
    __tablename__="evidence_entities"
    id:Mapped[int]=mapped_column(primary_key=True)
    entity_type:Mapped[str]=mapped_column(String(32))
    canonical_name:Mapped[str]=mapped_column(Text)
    normalized_name:Mapped[str]=mapped_column(Text)
    external_ids:Mapped[dict]=mapped_column(JSON,default=dict)
    metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
    __table_args__=(UniqueConstraint("entity_type","normalized_name"),)

class LegislativeEntityLink(Base):
    __tablename__="legislative_entity_links"
    id:Mapped[int]=mapped_column(primary_key=True)
    bill_id:Mapped[int]=mapped_column(ForeignKey("bills.id",ondelete="CASCADE"))
    section_id:Mapped[int|None]=mapped_column(ForeignKey("sections.id",ondelete="CASCADE"),nullable=True)
    entity_id:Mapped[int]=mapped_column(ForeignKey("evidence_entities.id",ondelete="CASCADE"))
    link_type:Mapped[str]=mapped_column(String(64))
    evidence:Mapped[str]=mapped_column(Text)
    source_url:Mapped[str|None]=mapped_column(Text,nullable=True)
    confidence:Mapped[float]=mapped_column(Float,default=1.0)
    extraction_method:Mapped[str]=mapped_column(String(64),default="deterministic")
    metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
    __table_args__=(UniqueConstraint("bill_id","section_id","entity_id","link_type"),)

class EntityRelationship(Base):
    __tablename__="entity_relationships"
    id:Mapped[int]=mapped_column(primary_key=True)
    source_entity_id:Mapped[int]=mapped_column(ForeignKey("evidence_entities.id",ondelete="CASCADE"))
    target_entity_id:Mapped[int]=mapped_column(ForeignKey("evidence_entities.id",ondelete="CASCADE"))
    relation_type:Mapped[str]=mapped_column(String(64))
    evidence:Mapped[str]=mapped_column(Text)
    source_url:Mapped[str|None]=mapped_column(Text,nullable=True)
    observed_on:Mapped[str|None]=mapped_column(String(32),nullable=True)
    confidence:Mapped[float]=mapped_column(Float,default=1.0)
    source_system:Mapped[str]=mapped_column(String(64),default="manual")
    metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
    __table_args__=(UniqueConstraint("source_entity_id","target_entity_id","relation_type","source_url"),)
