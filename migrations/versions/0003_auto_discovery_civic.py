"""Add automatic discovery and civic source storage.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision="0003"
down_revision="0002"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table(
        "discovery_cursors",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("source_key",sa.String(160),nullable=False,unique=True),
        sa.Column("jurisdiction",sa.String(32),nullable=False),
        sa.Column("session",sa.String(64),nullable=True),
        sa.Column("cursor_json",sa.JSON(),nullable=False),
        sa.Column("cycle",sa.Integer(),nullable=False),
        sa.Column("status",sa.String(32),nullable=False),
        sa.Column("last_started_at",sa.DateTime(),nullable=True),
        sa.Column("last_completed_at",sa.DateTime(),nullable=True),
        sa.Column("last_error",sa.Text(),nullable=True),
        sa.Column("updated_at",sa.DateTime(),nullable=False),
    )
    op.create_index("ix_discovery_cursor_status","discovery_cursors",["status","updated_at"])
    op.create_table(
        "civic_documents",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("source_key",sa.String(160),nullable=False),
        sa.Column("jurisdiction",sa.String(64),nullable=False),
        sa.Column("governing_body",sa.String(160),nullable=False),
        sa.Column("document_type",sa.String(64),nullable=False),
        sa.Column("title",sa.Text(),nullable=False),
        sa.Column("meeting_date",sa.String(32),nullable=True),
        sa.Column("source_url",sa.Text(),nullable=False),
        sa.Column("external_id",sa.String(240),nullable=False),
        sa.Column("text",sa.Text(),nullable=True),
        sa.Column("sha256",sa.String(64),nullable=True),
        sa.Column("metadata_json",sa.JSON(),nullable=False),
        sa.Column("first_seen_at",sa.DateTime(),nullable=False),
        sa.Column("last_seen_at",sa.DateTime(),nullable=False),
        sa.UniqueConstraint("source_key","external_id"),
    )
    op.create_index("ix_civic_documents_source_date","civic_documents",["source_key","meeting_date"])
    op.create_index("ix_civic_documents_body_date","civic_documents",["governing_body","meeting_date"])

def downgrade():
    op.drop_index("ix_civic_documents_body_date",table_name="civic_documents")
    op.drop_index("ix_civic_documents_source_date",table_name="civic_documents")
    op.drop_table("civic_documents")
    op.drop_index("ix_discovery_cursor_status",table_name="discovery_cursors")
    op.drop_table("discovery_cursors")
