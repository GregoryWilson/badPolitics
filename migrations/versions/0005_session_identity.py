"""Distinguish regular and called legislative sessions.

Revision ID: 0005
Revises: 0004
"""
import json

from alembic import op
import sqlalchemy as sa

revision="0005"
down_revision="0004"
branch_labels=None
depends_on=None

NAMING_CONVENTION={"uq":"uq_%(table_name)s_%(column_0_N_name)s"}

def _unique_name(table,columns):
    inspector=sa.inspect(op.get_bind())
    target=list(columns)
    for constraint in inspector.get_unique_constraints(table):
        if list(constraint.get("column_names") or [])==target:
            return constraint.get("name")
    return None

def upgrade():
    bind=op.get_bind()
    op.add_column("bills",sa.Column("session_code",sa.String(64),nullable=True))

    rows=bind.execute(sa.text(
        "SELECT id, jurisdiction, congress, metadata_json FROM bills"
    )).mappings().all()
    for row in rows:
        metadata=row["metadata_json"] or {}
        if isinstance(metadata,str):
            try:
                metadata=json.loads(metadata)
            except Exception:
                metadata={}
        session=(metadata or {}).get("jurisdiction_session") or str(row["congress"])
        bind.execute(
            sa.text("UPDATE bills SET session_code=:session WHERE id=:id"),
            {"session":str(session),"id":row["id"]},
        )

    dialect=bind.dialect.name
    old_bill_name=_unique_name(
        "bills",["jurisdiction","congress","bill_type","bill_number"]
    )
    if not old_bill_name and dialect=="sqlite":
        old_bill_name="uq_bills_jurisdiction_congress_bill_type_bill_number"
    with op.batch_alter_table(
        "bills",
        recreate="always" if dialect=="sqlite" else "auto",
        naming_convention=NAMING_CONVENTION,
    ) as batch:
        if old_bill_name:
            batch.drop_constraint(old_bill_name,type_="unique")
        batch.alter_column(
            "session_code",
            existing_type=sa.String(64),
            nullable=False,
        )
        batch.create_unique_constraint(
            "uq_bills_jurisdiction_session_code_bill_type_bill_number",
            ["jurisdiction","session_code","bill_type","bill_number"],
        )

    old_amendment_name=_unique_name(
        "amendments",["congress","amendment_type","amendment_number"]
    )
    if not old_amendment_name and dialect=="sqlite":
        old_amendment_name="uq_amendments_congress_amendment_type_amendment_number"
    with op.batch_alter_table(
        "amendments",
        recreate="always" if dialect=="sqlite" else "auto",
        naming_convention=NAMING_CONVENTION,
    ) as batch:
        if old_amendment_name:
            batch.drop_constraint(old_amendment_name,type_="unique")
        batch.create_unique_constraint(
            "uq_amendments_bill_id_amendment_type_amendment_number",
            ["bill_id","amendment_type","amendment_number"],
        )

def downgrade():
    bind=op.get_bind()
    dialect=bind.dialect.name

    current_amendment_name=_unique_name(
        "amendments",["bill_id","amendment_type","amendment_number"]
    )
    with op.batch_alter_table(
        "amendments",
        recreate="always" if dialect=="sqlite" else "auto",
        naming_convention=NAMING_CONVENTION,
    ) as batch:
        if current_amendment_name:
            batch.drop_constraint(current_amendment_name,type_="unique")
        batch.create_unique_constraint(
            "uq_amendments_congress_amendment_type_amendment_number",
            ["congress","amendment_type","amendment_number"],
        )

    current_bill_name=_unique_name(
        "bills",["jurisdiction","session_code","bill_type","bill_number"]
    )
    with op.batch_alter_table(
        "bills",
        recreate="always" if dialect=="sqlite" else "auto",
        naming_convention=NAMING_CONVENTION,
    ) as batch:
        if current_bill_name:
            batch.drop_constraint(current_bill_name,type_="unique")
        batch.create_unique_constraint(
            "uq_bills_jurisdiction_congress_bill_type_bill_number",
            ["jurisdiction","congress","bill_type","bill_number"],
        )
        batch.drop_column("session_code")
