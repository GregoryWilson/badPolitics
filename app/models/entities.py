from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, JSON, UniqueConstraint, Float, Index
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
    documents=relationship("LegislativeDocument",back_populates="bill",cascade="all,delete-orphan")
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
    __table_args__=(UniqueConstraint("bill_id","action_date","text"),Index("ix_bill_actions_bill_date","bill_id","action_date"),)

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
    __table_args__=(Index("ix_sections_version_number","version_id","section_number"),)

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
    __table_args__=(Index("ix_findings_version_section","version_id","section_id"),)


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
    __table_args__=(
        UniqueConstraint("bill_id","section_id","entity_id","link_type"),
        Index("ix_legislative_links_bill_section","bill_id","section_id"),
        Index("ix_legislative_links_entity","entity_id"),
    )

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
    __table_args__=(
        UniqueConstraint("source_entity_id","target_entity_id","relation_type","source_url"),
        Index("ix_relationships_source","source_entity_id"),
        Index("ix_relationships_target","target_entity_id"),
    )


class ExternalEvidenceRecord(Base):
    __tablename__="external_evidence_records"
    id:Mapped[int]=mapped_column(primary_key=True)
    source_system:Mapped[str]=mapped_column(String(64))
    record_type:Mapped[str]=mapped_column(String(64))
    external_id:Mapped[str]=mapped_column(String(160))
    observed_on:Mapped[str|None]=mapped_column(String(32),nullable=True)
    source_url:Mapped[str|None]=mapped_column(Text,nullable=True)
    raw_json:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(
        UniqueConstraint("source_system","record_type","external_id"),
        Index("ix_external_evidence_source_type_observed","source_system","record_type","observed_on"),
    )


class CorrelationFinding(Base):
    __tablename__="correlation_findings"
    id:Mapped[int]=mapped_column(primary_key=True)
    bill_id:Mapped[int]=mapped_column(ForeignKey("bills.id",ondelete="CASCADE"))
    legislative_entity_id:Mapped[int]=mapped_column(ForeignKey("evidence_entities.id",ondelete="CASCADE"))
    matched_entity_id:Mapped[int]=mapped_column(ForeignKey("evidence_entities.id",ondelete="CASCADE"))
    match_basis:Mapped[str]=mapped_column(String(32))
    confidence:Mapped[float]=mapped_column(Float,default=0)
    evidence:Mapped[str]=mapped_column(Text)
    metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(UniqueConstraint("bill_id","legislative_entity_id","matched_entity_id","match_basis"),)


class ResearchRun(Base):
    __tablename__="research_runs"
    id:Mapped[int]=mapped_column(primary_key=True)
    bill_id:Mapped[int]=mapped_column(ForeignKey("bills.id",ondelete="CASCADE"))
    status:Mapped[str]=mapped_column(String(32),default="running")
    started_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    completed_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    summary_json:Mapped[dict]=mapped_column(JSON,default=dict)

class ResearchStep(Base):
    __tablename__="research_steps"
    id:Mapped[int]=mapped_column(primary_key=True)
    run_id:Mapped[int]=mapped_column(ForeignKey("research_runs.id",ondelete="CASCADE"))
    entity_id:Mapped[int|None]=mapped_column(ForeignKey("evidence_entities.id",ondelete="CASCADE"),nullable=True)
    source_system:Mapped[str]=mapped_column(String(64))
    action:Mapped[str]=mapped_column(String(64))
    status:Mapped[str]=mapped_column(String(32))
    reason:Mapped[str]=mapped_column(Text)
    result_json:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)


class InvestigationReport(Base):
    __tablename__="investigation_reports"
    id:Mapped[int]=mapped_column(primary_key=True)
    bill_id:Mapped[int]=mapped_column(ForeignKey("bills.id",ondelete="CASCADE"))
    research_run_id:Mapped[int|None]=mapped_column(ForeignKey("research_runs.id",ondelete="SET NULL"),nullable=True)
    status:Mapped[str]=mapped_column(String(32),default="complete")
    report_json:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)


class WatchRule(Base):
    __tablename__="watch_rules"
    id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(Text)
    target_type:Mapped[str]=mapped_column(String(32))
    jurisdiction:Mapped[str]=mapped_column(String(32),default="US")
    congress:Mapped[int|None]=mapped_column(Integer,nullable=True)
    bill_type:Mapped[str|None]=mapped_column(String(16),nullable=True)
    bill_number:Mapped[str|None]=mapped_column(String(32),nullable=True)
    active:Mapped[bool]=mapped_column(default=True)
    auto_research:Mapped[bool]=mapped_column(default=False)
    auto_report:Mapped[bool]=mapped_column(default=False)
    metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    last_scanned_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)

class WatchScan(Base):
    __tablename__="watch_scans"
    id:Mapped[int]=mapped_column(primary_key=True)
    watch_rule_id:Mapped[int]=mapped_column(ForeignKey("watch_rules.id",ondelete="CASCADE"))
    status:Mapped[str]=mapped_column(String(32),default="running")
    started_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    completed_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    summary_json:Mapped[dict]=mapped_column(JSON,default=dict)

class WatchEvent(Base):
    __tablename__="watch_events"
    id:Mapped[int]=mapped_column(primary_key=True)
    watch_rule_id:Mapped[int]=mapped_column(ForeignKey("watch_rules.id",ondelete="CASCADE"))
    watch_scan_id:Mapped[int]=mapped_column(ForeignKey("watch_scans.id",ondelete="CASCADE"))
    bill_id:Mapped[int|None]=mapped_column(ForeignKey("bills.id",ondelete="CASCADE"),nullable=True)
    event_type:Mapped[str]=mapped_column(String(64))
    event_key:Mapped[str]=mapped_column(String(200))
    title:Mapped[str]=mapped_column(Text)
    detail_json:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(UniqueConstraint("watch_rule_id","event_type","event_key"),)


class LegislativeDocument(Base):
    __tablename__="legislative_documents"
    id:Mapped[int]=mapped_column(primary_key=True)
    bill_id:Mapped[int]=mapped_column(ForeignKey("bills.id",ondelete="CASCADE"))
    document_type:Mapped[str]=mapped_column(String(64))
    description:Mapped[str|None]=mapped_column(Text,nullable=True)
    source_url:Mapped[str]=mapped_column(Text)
    source_system:Mapped[str]=mapped_column(String(64))
    issued_on:Mapped[str|None]=mapped_column(String(32),nullable=True)
    format:Mapped[str]=mapped_column(String(32),default="html")
    text:Mapped[str|None]=mapped_column(Text,nullable=True)
    sha256:Mapped[str|None]=mapped_column(String(64),nullable=True)
    metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    bill=relationship("Bill",back_populates="documents")
    __table_args__=(UniqueConstraint("bill_id","document_type","source_url"),)


class ComparativeFinding(Base):
    __tablename__="comparative_findings"
    id:Mapped[int]=mapped_column(primary_key=True)
    bill_id:Mapped[int]=mapped_column(ForeignKey("bills.id",ondelete="CASCADE"))
    document_id:Mapped[int|None]=mapped_column(ForeignKey("legislative_documents.id",ondelete="CASCADE"),nullable=True)
    category:Mapped[str]=mapped_column(String(64))
    confidence:Mapped[float]=mapped_column(Float,default=0)
    statement:Mapped[str]=mapped_column(Text)
    evidence:Mapped[str]=mapped_column(Text)
    source_kind:Mapped[str]=mapped_column(String(32),default="bill_text")
    evidence_hash:Mapped[str]=mapped_column(String(64))
    metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(UniqueConstraint("bill_id","document_id","category","evidence_hash"),)


class ProvisionLineage(Base):
    __tablename__="provision_lineage"
    id:Mapped[int]=mapped_column(primary_key=True)
    bill_id:Mapped[int]=mapped_column(ForeignKey("bills.id",ondelete="CASCADE"))
    section_number:Mapped[str]=mapped_column(String(64))
    from_version_id:Mapped[int|None]=mapped_column(ForeignKey("bill_versions.id",ondelete="CASCADE"),nullable=True)
    to_version_id:Mapped[int]=mapped_column(ForeignKey("bill_versions.id",ondelete="CASCADE"))
    event_type:Mapped[str]=mapped_column(String(32))
    similarity:Mapped[float|None]=mapped_column(Float,nullable=True)
    old_text:Mapped[str|None]=mapped_column(Text,nullable=True)
    new_text:Mapped[str|None]=mapped_column(Text,nullable=True)
    diff_text:Mapped[str|None]=mapped_column(Text,nullable=True)
    metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(
        UniqueConstraint("bill_id","section_number","from_version_id","to_version_id","event_type"),
        Index("ix_lineage_bill_to_version","bill_id","to_version_id"),
    )

class AmendmentAttribution(Base):
    __tablename__="amendment_attributions"
    id:Mapped[int]=mapped_column(primary_key=True)
    lineage_id:Mapped[int]=mapped_column(ForeignKey("provision_lineage.id",ondelete="CASCADE"))
    amendment_id:Mapped[int]=mapped_column(ForeignKey("amendments.id",ondelete="CASCADE"))
    attribution_type:Mapped[str]=mapped_column(String(32),default="candidate")
    confidence:Mapped[float]=mapped_column(Float,default=0)
    evidence:Mapped[str]=mapped_column(Text)
    metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(UniqueConstraint("lineage_id","amendment_id","attribution_type"),)


class ScopeFinding(Base):
    __tablename__="scope_findings"
    id:Mapped[int]=mapped_column(primary_key=True)
    bill_id:Mapped[int]=mapped_column(ForeignKey("bills.id",ondelete="CASCADE"))
    version_id:Mapped[int]=mapped_column(ForeignKey("bill_versions.id",ondelete="CASCADE"))
    section_id:Mapped[int]=mapped_column(ForeignKey("sections.id",ondelete="CASCADE"))
    category:Mapped[str]=mapped_column(String(64))
    confidence:Mapped[float]=mapped_column(Float,default=0)
    anchor_similarity:Mapped[float|None]=mapped_column(Float,nullable=True)
    peer_similarity:Mapped[float|None]=mapped_column(Float,nullable=True)
    statement:Mapped[str]=mapped_column(Text)
    evidence:Mapped[str]=mapped_column(Text)
    metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(UniqueConstraint("bill_id","version_id","section_id","category"),)


class ProvisionEvidencePacket(Base):
    __tablename__="provision_evidence_packets"
    id:Mapped[int]=mapped_column(primary_key=True)
    bill_id:Mapped[int]=mapped_column(ForeignKey("bills.id",ondelete="CASCADE"))
    version_id:Mapped[int]=mapped_column(ForeignKey("bill_versions.id",ondelete="CASCADE"))
    section_id:Mapped[int]=mapped_column(ForeignKey("sections.id",ondelete="CASCADE"))
    packet_hash:Mapped[str]=mapped_column(String(64))
    packet_json:Mapped[dict]=mapped_column(JSON,default=dict)
    narrative:Mapped[str|None]=mapped_column(Text,nullable=True)
    llm_model:Mapped[str|None]=mapped_column(String(128),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(UniqueConstraint("bill_id","version_id","section_id","packet_hash"),)


class InvestigationQueueItem(Base):
    __tablename__="investigation_queue_items"
    id:Mapped[int]=mapped_column(primary_key=True)
    bill_id:Mapped[int]=mapped_column(ForeignKey("bills.id",ondelete="CASCADE"))
    version_id:Mapped[int]=mapped_column(ForeignKey("bill_versions.id",ondelete="CASCADE"))
    section_id:Mapped[int]=mapped_column(ForeignKey("sections.id",ondelete="CASCADE"))
    packet_id:Mapped[int]=mapped_column(ForeignKey("provision_evidence_packets.id",ondelete="CASCADE"))
    packet_hash:Mapped[str]=mapped_column(String(64))
    status:Mapped[str]=mapped_column(String(32),default="new")
    trigger_types:Mapped[list]=mapped_column(JSON,default=list)
    evidence_coverage:Mapped[dict]=mapped_column(JSON,default=dict)
    unresolved_gaps:Mapped[list]=mapped_column(JSON,default=list)
    analyst_notes:Mapped[str|None]=mapped_column(Text,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    last_seen_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(
        UniqueConstraint("bill_id","version_id","section_id","packet_hash"),
        Index("ix_queue_status_updated","status","updated_at"),
        Index("ix_queue_bill_status_updated","bill_id","status","updated_at"),
    )


class DiscoveryCursor(Base):
    __tablename__="discovery_cursors"
    id:Mapped[int]=mapped_column(primary_key=True)
    source_key:Mapped[str]=mapped_column(String(160),unique=True)
    jurisdiction:Mapped[str]=mapped_column(String(32))
    session:Mapped[str|None]=mapped_column(String(64),nullable=True)
    cursor_json:Mapped[dict]=mapped_column(JSON,default=dict)
    cycle:Mapped[int]=mapped_column(Integer,default=1)
    status:Mapped[str]=mapped_column(String(32),default="idle")
    last_started_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    last_completed_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    last_error:Mapped[str|None]=mapped_column(Text,nullable=True)
    updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(Index("ix_discovery_cursor_status","status","updated_at"),)

class CivicDocument(Base):
    __tablename__="civic_documents"
    id:Mapped[int]=mapped_column(primary_key=True)
    source_key:Mapped[str]=mapped_column(String(160))
    jurisdiction:Mapped[str]=mapped_column(String(64))
    governing_body:Mapped[str]=mapped_column(String(160))
    document_type:Mapped[str]=mapped_column(String(64))
    title:Mapped[str]=mapped_column(Text)
    meeting_date:Mapped[str|None]=mapped_column(String(32),nullable=True)
    source_url:Mapped[str]=mapped_column(Text)
    external_id:Mapped[str]=mapped_column(String(240))
    text:Mapped[str|None]=mapped_column(Text,nullable=True)
    sha256:Mapped[str|None]=mapped_column(String(64),nullable=True)
    metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
    first_seen_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    last_seen_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(
        UniqueConstraint("source_key","external_id"),
        Index("ix_civic_documents_source_date","source_key","meeting_date"),
        Index("ix_civic_documents_body_date","governing_body","meeting_date"),
    )


class CivicDocumentRevision(Base):
    __tablename__="civic_document_revisions"
    id:Mapped[int]=mapped_column(primary_key=True)
    civic_document_id:Mapped[int]=mapped_column(ForeignKey("civic_documents.id",ondelete="CASCADE"))
    sha256:Mapped[str]=mapped_column(String(64))
    text:Mapped[str|None]=mapped_column(Text,nullable=True)
    metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
    observed_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(
        UniqueConstraint("civic_document_id","sha256"),
        Index("ix_civic_revisions_document_observed","civic_document_id","observed_at"),
    )


class CivicAgendaItem(Base):
    __tablename__="civic_agenda_items"
    id:Mapped[int]=mapped_column(primary_key=True)
    civic_document_id:Mapped[int]=mapped_column(ForeignKey("civic_documents.id",ondelete="CASCADE"))
    revision_id:Mapped[int|None]=mapped_column(ForeignKey("civic_document_revisions.id",ondelete="CASCADE"),nullable=True)
    ordinal:Mapped[int]=mapped_column(Integer)
    item_number:Mapped[str|None]=mapped_column(String(64),nullable=True)
    heading:Mapped[str|None]=mapped_column(Text,nullable=True)
    text:Mapped[str]=mapped_column(Text)
    evidence_hash:Mapped[str]=mapped_column(String(64))
    metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(
        UniqueConstraint("civic_document_id","revision_id","evidence_hash"),
        Index("ix_civic_agenda_document_ordinal","civic_document_id","ordinal"),
    )

class CivicFinding(Base):
    __tablename__="civic_findings"
    id:Mapped[int]=mapped_column(primary_key=True)
    civic_document_id:Mapped[int]=mapped_column(ForeignKey("civic_documents.id",ondelete="CASCADE"))
    revision_id:Mapped[int|None]=mapped_column(ForeignKey("civic_document_revisions.id",ondelete="CASCADE"),nullable=True)
    agenda_item_id:Mapped[int|None]=mapped_column(ForeignKey("civic_agenda_items.id",ondelete="CASCADE"),nullable=True)
    category:Mapped[str]=mapped_column(String(64))
    statement:Mapped[str]=mapped_column(Text)
    evidence:Mapped[str]=mapped_column(Text)
    confidence:Mapped[float]=mapped_column(Float,default=1.0)
    evidence_hash:Mapped[str]=mapped_column(String(64))
    metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(
        UniqueConstraint("civic_document_id","revision_id","agenda_item_id","category","evidence_hash"),
        Index("ix_civic_findings_document_category","civic_document_id","category"),
    )

class CivicEntityLink(Base):
    __tablename__="civic_entity_links"
    id:Mapped[int]=mapped_column(primary_key=True)
    civic_document_id:Mapped[int]=mapped_column(ForeignKey("civic_documents.id",ondelete="CASCADE"))
    revision_id:Mapped[int|None]=mapped_column(ForeignKey("civic_document_revisions.id",ondelete="CASCADE"),nullable=True)
    agenda_item_id:Mapped[int|None]=mapped_column(ForeignKey("civic_agenda_items.id",ondelete="CASCADE"),nullable=True)
    entity_id:Mapped[int]=mapped_column(ForeignKey("evidence_entities.id",ondelete="CASCADE"))
    link_type:Mapped[str]=mapped_column(String(64))
    evidence:Mapped[str]=mapped_column(Text)
    confidence:Mapped[float]=mapped_column(Float,default=1.0)
    metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(
        UniqueConstraint("civic_document_id","revision_id","agenda_item_id","entity_id","link_type"),
        Index("ix_civic_entity_document","civic_document_id","entity_id"),
    )
