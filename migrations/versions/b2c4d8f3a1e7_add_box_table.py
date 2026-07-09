"""Add Box table for hardware status updates

Revision ID: b2c4d8f3a1e7
Revises: 9d200740c874
Create Date: 2026-05-21 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b2c4d8f3a1e7"
down_revision = "af3c2d4e5f61"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "boxes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name=op.f("uq_boxes_name")),
    )
    op.create_index(op.f("ix_boxes_name"), "boxes", ["name"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_boxes_name"), table_name="boxes")
    op.drop_table("boxes")
