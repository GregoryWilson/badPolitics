"""Add civic analysis records.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision="0004"
down_revision="0003"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table(
        "civic_agenda_items",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("civic_document_id",sa.Integer(),sa.ForeignKey("civic_documents.id",ondelete="CASCADE"),nullable=False),
        sa.Column("revision_id",sa.Integer(),sa.ForeignKey("civic_document_revisions.id",ondelete="CASCADE"),nullable=True),
        sa.Column("ordinal",sa.Integer(),nullable=False),
        sa.Column("item_number",sa.String(64),nullable=True),
        sa.Column("heading",sa.Text(),nullable=True),
        sa.Column("text",sa.Text(),nullable=False),
        sa.Column("evidence_hash",sa.String(64),nullable=False),
        sa.Column("metadata_json",sa.JSON(),nullable=False),
        sa.Column("created_at",sa.DateTime(),nullable=False),
        sa.UniqueConstraint("civic_document_id","revision_id","evidence_hash"),
    )
    op.create_index("ix_civic_agenda_document_ordinal","civic_agenda_items",["civic_document_id","ordinal"])
    op.create_table(
        "civic_findings",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("civic_document_id",sa.Integer(),sa.ForeignKey("civic_documents.id",ondelete="CASCADE"),nullable=False),
        sa.Column("revision_id",sa.Integer(),sa.ForeignKey("civic_document_revisions.id",ondelete="CASCADE"),nullable=True),
        sa.Column("agenda_item_id",sa.Integer(),sa.ForeignKey("civic_agenda_items.id",ondelete="CASCADE"),nullable=True),
        sa.Column("category",sa.String(64),nullable=False),
        sa.Column("statement",sa.Text(),nullable=False),
        sa.Column("evidence",sa.Text(),nullable=False),
        sa.Column("confidence",sa.Float(),nullable=False),
        sa.Column("evidence_hash",sa.String(64),nullable=False),
        sa.Column("metadata_json",sa.JSON(),nullable=False),
        sa.Column("created_at",sa.DateTime(),nullable=False),
        sa.UniqueConstraint("civic_document_id","revision_id","agenda_item_id","category","evidence_hash"),
    )
    op.create_index("ix_civic_findings_document_category","civic_findings",["civic_document_id","category"])
    op.create_table(
        "civic_entity_links",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("civic_document_id",sa.Integer(),sa.ForeignKey("civic_documents.id",ondelete="CASCADE"),nullable=False),
        sa.Column("revision_id",sa.Integer(),sa.ForeignKey("civic_document_revisions.id",ondelete="CASCADE"),nullable=True),
        sa.Column("agenda_item_id",sa.Integer(),sa.ForeignKey("civic_agenda_items.id",ondelete="CASCADE"),nullable=True),
        sa.Column("entity_id",sa.Integer(),sa.ForeignKey("evidence_entities.id",ondelete="CASCADE"),nullable=False),
        sa.Column("link_type",sa.String(64),nullable=False),
        sa.Column("evidence",sa.Text(),nullable=False),
        sa.Column("confidence",sa.Float(),nullable=False),
        sa.Column("metadata_json",sa.JSON(),nullable=False),
        sa.Column("created_at",sa.DateTime(),nullable=False),
        sa.UniqueConstraint("civic_document_id","revision_id","agenda_item_id","entity_id","link_type"),
    )
    op.create_index("ix_civic_entity_document","civic_entity_links",["civic_document_id","entity_id"])

def downgrade():
    op.drop_index("ix_civic_entity_document",table_name="civic_entity_links")
    op.drop_table("civic_entity_links")
    op.drop_index("ix_civic_findings_document_category",table_name="civic_findings")
    op.drop_table("civic_findings")
    op.drop_index("ix_civic_agenda_document_ordinal",table_name="civic_agenda_items")
    op.drop_table("civic_agenda_items")
