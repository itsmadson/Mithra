"""audit events

Append-only record of who changed what. The index churn autogenerate also
found is left-over naming from the jobs->runs rename and is handled
separately, so this migration adds one table and nothing else.

Revision ID: 7d68844c2dba
Revises: b1a2c3d4e5f6
Create Date: 2026-08-16 22:09:32.947376

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7d68844c2dba'
down_revision: Union[str, Sequence[str], None] = 'b1a2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the audit table."""
    op.create_table(
        "audit_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=True),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=True),
        sa.Column("subject_id", sa.String(length=64), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        # The account may go; what it did stays, with the email copied in.
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_events_action"), "audit_events", ["action"])
    op.create_index(op.f("ix_audit_events_created_at"), "audit_events", ["created_at"])
    op.create_index(op.f("ix_audit_events_org_id"), "audit_events", ["org_id"])


def downgrade() -> None:
    """Drop the audit table."""
    op.drop_index(op.f("ix_audit_events_org_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_created_at"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_action"), table_name="audit_events")
    op.drop_table("audit_events")
