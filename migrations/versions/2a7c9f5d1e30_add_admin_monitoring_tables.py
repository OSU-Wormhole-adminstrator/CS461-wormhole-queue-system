"""add admin monitoring tables

Revision ID: 2a7c9f5d1e30
Revises: af3c2d4e5f61
Create Date: 2026-05-21 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "2a7c9f5d1e30"
down_revision = "af3c2d4e5f61"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assistant_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_start", sa.DateTime(), nullable=False),
        sa.Column("session_end", sa.DateTime(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("assistant_sessions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_assistant_sessions_session_start"),
            ["session_start"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_assistant_sessions_user_id"),
            ["user_id"],
            unique=False,
        )

    op.create_table(
        "idle_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(), nullable=False),
        sa.Column("open_ticket_count", sa.Integer(), nullable=False),
        sa.Column("oldest_ticket_wait_minutes", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("idle_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_idle_events_triggered_at"),
            ["triggered_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_idle_events_user_id"),
            ["user_id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("idle_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_idle_events_user_id"))
        batch_op.drop_index(batch_op.f("ix_idle_events_triggered_at"))

    op.drop_table("idle_events")

    with op.batch_alter_table("assistant_sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_assistant_sessions_user_id"))
        batch_op.drop_index(batch_op.f("ix_assistant_sessions_session_start"))

    op.drop_table("assistant_sessions")
