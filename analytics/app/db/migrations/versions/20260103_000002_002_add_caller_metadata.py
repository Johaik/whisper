"""Add caller metadata columns

Revision ID: 002
Revises: 001
Create Date: 2026-01-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add caller metadata columns to recordings table
    op.add_column('recordings', sa.Column('phone_number', sa.String(32), nullable=True))
    op.add_column('recordings', sa.Column('caller_name', sa.String(256), nullable=True))
    op.add_column('recordings', sa.Column('call_datetime', sa.DateTime(), nullable=True))
    
    # Add index on phone_number for lookups
    op.create_index('ix_recordings_phone_number', 'recordings', ['phone_number'])


def downgrade() -> None:
    op.drop_index('ix_recordings_phone_number', 'recordings')
    op.drop_column('recordings', 'call_datetime')
    op.drop_column('recordings', 'caller_name')
    op.drop_column('recordings', 'phone_number')

