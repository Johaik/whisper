"""SQLAlchemy ORM models for the transcription pipeline."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    type_annotation_map = {
        dict[str, Any]: JSONB,
    }


class RecordingStatus(str, enum.Enum):
    """Status of a recording in the processing pipeline."""

    DISCOVERED = "discovered"
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class Recording(Base):
    """A recording file discovered in the calls directory."""

    __tablename__ = "recordings"
    __table_args__ = (
        UniqueConstraint("file_hash", name="uq_recordings_file_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)

    status: Mapped[RecordingStatus] = mapped_column(
        Enum(
            RecordingStatus,
            name="recordingstatus",
            create_constraint=False,
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=RecordingStatus.DISCOVERED,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # Audio metadata (populated by ffprobe)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    codec: Mapped[str | None] = mapped_column(String(64), nullable=True)
    container: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bit_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Additional metadata as JSON
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Caller metadata (parsed from filename)
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    caller_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    call_datetime: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    transcript: Mapped["Transcript | None"] = relationship(
        back_populates="recording", uselist=False, cascade="all, delete-orphan"
    )
    enrichment: Mapped["Enrichment | None"] = relationship(
        back_populates="recording", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Recording {self.file_name} ({self.status.value})>"


class Transcript(Base):
    """Transcription result for a recording."""

    __tablename__ = "transcripts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    recording_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recordings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Model info
    model_name: Mapped[str] = mapped_column(String(256), nullable=False)
    beam_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compute_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Transcription result
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="he")
    language_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # Segments with timing and optional speaker info
    segments_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )

    # Raw transcript output for debugging/reprocessing
    transcript_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Relationship
    recording: Mapped["Recording"] = relationship(back_populates="transcript")

    def __repr__(self) -> str:
        return f"<Transcript for {self.recording_id}>"


class Enrichment(Base):
    """Analytics and enrichment data for a recording."""

    __tablename__ = "enrichments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    recording_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recordings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Diarization info
    speaker_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diarization_enabled: Mapped[bool] = mapped_column(default=False)
    diarization_pending: Mapped[bool] = mapped_column(default=False)  # True if skipped due to duration
    diarization_skip_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Talk/silence analytics
    total_speech_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_silence_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    talk_time_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    silence_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Segment analytics
    segment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_segment_length: Mapped[float | None] = mapped_column(Float, nullable=True)
    speaker_turns: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Long silence events (silence > threshold)
    long_silence_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    long_silence_threshold_sec: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Full analytics as JSON
    analytics_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Relationship
    recording: Mapped["Recording"] = relationship(back_populates="enrichment")

    def __repr__(self) -> str:
        return f"<Enrichment for {self.recording_id}>"

