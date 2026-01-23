"""Add diarization pending columns

Revision ID: 003
Revises: 002
Create Date: 2026-01-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add diarization pending columns to enrichments table
    op.add_column('enrichments', sa.Column('diarization_pending', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('enrichments', sa.Column('diarization_skip_reason', sa.String(256), nullable=True))


def downgrade() -> None:
    op.drop_column('enrichments', 'diarization_skip_reason')
    op.drop_column('enrichments', 'diarization_pending')
