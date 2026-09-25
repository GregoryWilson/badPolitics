"""Index dated actions used by the weekly institution dashboard.

Revision ID: 0006
Revises: 0005
"""
from alembic import op

revision="0006"
down_revision="0005"
branch_labels=None
depends_on=None

def upgrade():
    op.create_index("ix_bill_actions_date_bill","bill_actions",["action_date","bill_id"])

def downgrade():
    op.drop_index("ix_bill_actions_date_bill",table_name="bill_actions")
