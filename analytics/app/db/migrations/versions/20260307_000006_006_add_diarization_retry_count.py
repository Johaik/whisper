"""Add diarization_retry_count to enrichments

Revision ID: 006
Revises: 005
Create Date: 2026-03-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add diarization_retry_count to enrichments table
    op.add_column('enrichments', sa.Column('diarization_retry_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('enrichments', 'diarization_retry_count')
