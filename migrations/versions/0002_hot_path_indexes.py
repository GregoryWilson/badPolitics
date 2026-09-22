"""Add hot-path query indexes.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision="0002"
down_revision="0001"
branch_labels=None
depends_on=None

INDEXES=[
    ("ix_bill_actions_bill_date","bill_actions",["bill_id","action_date"]),
    ("ix_sections_version_number","sections",["version_id","section_number"]),
    ("ix_findings_version_section","findings",["version_id","section_id"]),
    ("ix_legislative_links_bill_section","legislative_entity_links",["bill_id","section_id"]),
    ("ix_legislative_links_entity","legislative_entity_links",["entity_id"]),
    ("ix_relationships_source","entity_relationships",["source_entity_id"]),
    ("ix_relationships_target","entity_relationships",["target_entity_id"]),
    ("ix_external_evidence_source_type_observed","external_evidence_records",["source_system","record_type","observed_on"]),
    ("ix_lineage_bill_to_version","provision_lineage",["bill_id","to_version_id"]),
    ("ix_queue_status_updated","investigation_queue_items",["status","updated_at"]),
    ("ix_queue_bill_status_updated","investigation_queue_items",["bill_id","status","updated_at"]),
]

def _existing_indexes(table):
    return {row["name"] for row in sa.inspect(op.get_bind()).get_indexes(table)}

def upgrade():
    for name,table,columns in INDEXES:
        if name not in _existing_indexes(table):
            op.create_index(name,table,columns,unique=False)

def downgrade():
    for name,table,_ in reversed(INDEXES):
        if name in _existing_indexes(table):
            op.drop_index(name,table_name=table)
