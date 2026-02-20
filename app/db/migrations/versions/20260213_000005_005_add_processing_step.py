"""Add processing_step and processing_step_started_at to recordings

Revision ID: 005
Revises: 004
Create Date: 2026-02-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "recordings",
        sa.Column("processing_step", sa.String(64), nullable=True),
    )
    op.add_column(
        "recordings",
        sa.Column("processing_step_started_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recordings", "processing_step_started_at")
    op.drop_column("recordings", "processing_step")
