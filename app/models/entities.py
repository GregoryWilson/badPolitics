from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, JSON, UniqueConstraint, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class Bill(Base):
    __tablename__ = "bills"
    id: Mapped[int] = mapped_column(primary_key=True)
    jurisdiction: Mapped[str] = mapped_column(String(32), default="US")
    congress: Mapped[int] = mapped_column(Integer)
    bill_type: Mapped[str] = mapped_column(String(16))
    bill_number: Mapped[str] = mapped_column(String(32))
    title: Mapped[str | None] = mapped_column(Text)
    latest_action: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    versions = relationship("BillVersion", back_populates="bill", cascade="all,delete-orphan")
    __table_args__ = (UniqueConstraint("jurisdiction","congress","bill_type","bill_number"),)

class BillVersion(Base):
    __tablename__ = "bill_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"))
    version_code: Mapped[str] = mapped_column(String(64))
    version_name: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    issued_on: Mapped[str | None] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    bill = relationship("Bill", back_populates="versions")
    sections = relationship("Section", back_populates="version", cascade="all,delete-orphan")
    findings = relationship("Finding", back_populates="version", cascade="all,delete-orphan")
    __table_args__ = (UniqueConstraint("bill_id","version_code","sha256"),)

class Section(Base):
    __tablename__ = "sections"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("bill_versions.id", ondelete="CASCADE"))
    section_number: Mapped[str] = mapped_column(String(64))
    heading: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer)
    version = relationship("BillVersion", back_populates="sections")

class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("bill_versions.id", ondelete="CASCADE"))
    section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(String(64))
    severity: Mapped[float] = mapped_column(Float, default=0)
    label: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    version = relationship("BillVersion", back_populates="findings")
