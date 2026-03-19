"""Initial schema with recordings, transcripts, and enrichments tables.

Revision ID: 001
Revises: None
Create Date: 2026-01-03 00:00:01.000000+00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create recording status enum
    recording_status = postgresql.ENUM(
        "discovered", "queued", "processing", "done", "failed", "skipped",
        name="recordingstatus",
        create_type=True,
    )
    recording_status.create(op.get_bind(), checkfirst=True)

    # Create recordings table
    op.create_table(
        "recordings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("file_name", sa.String(length=512), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "discovered", "queued", "processing", "done", "failed", "skipped",
                name="recordingstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, default=0),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("sample_rate", sa.Integer(), nullable=True),
        sa.Column("channels", sa.Integer(), nullable=True),
        sa.Column("codec", sa.String(length=64), nullable=True),
        sa.Column("container", sa.String(length=64), nullable=True),
        sa.Column("bit_rate", sa.Integer(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_hash", name="uq_recordings_file_hash"),
    )
    op.create_index(op.f("ix_recordings_file_path"), "recordings", ["file_path"], unique=False)
    op.create_index(op.f("ix_recordings_status"), "recordings", ["status"], unique=False)

    # Create transcripts table
    op.create_table(
        "transcripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recording_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_name", sa.String(length=256), nullable=False),
        sa.Column("beam_size", sa.Integer(), nullable=True),
        sa.Column("compute_type", sa.String(length=32), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("language_probability", sa.Float(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("segments_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("transcript_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recordings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recording_id"),
    )

    # Create enrichments table
    op.create_table(
        "enrichments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recording_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("speaker_count", sa.Integer(), nullable=True),
        sa.Column("diarization_enabled", sa.Boolean(), nullable=False, default=False),
        sa.Column("total_speech_time", sa.Float(), nullable=True),
        sa.Column("total_silence_time", sa.Float(), nullable=True),
        sa.Column("talk_time_ratio", sa.Float(), nullable=True),
        sa.Column("silence_ratio", sa.Float(), nullable=True),
        sa.Column("segment_count", sa.Integer(), nullable=True),
        sa.Column("avg_segment_length", sa.Float(), nullable=True),
        sa.Column("speaker_turns", sa.Integer(), nullable=True),
        sa.Column("long_silence_count", sa.Integer(), nullable=True),
        sa.Column("long_silence_threshold_sec", sa.Float(), nullable=True),
        sa.Column("analytics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recordings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recording_id"),
    )


def downgrade() -> None:
    op.drop_table("enrichments")
    op.drop_table("transcripts")
    op.drop_index(op.f("ix_recordings_status"), table_name="recordings")
    op.drop_index(op.f("ix_recordings_file_path"), table_name="recordings")
    op.drop_table("recordings")

    # Drop the enum type
    postgresql.ENUM(name="recordingstatus").drop(op.get_bind(), checkfirst=True)

