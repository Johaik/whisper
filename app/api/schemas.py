"""Pydantic schemas for API request/response models."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import RecordingStatus


# Base schemas
class RecordingBase(BaseModel):
    """Base recording fields."""

    file_path: str
    file_name: str
    file_hash: str
    file_size: int


class TranscriptBase(BaseModel):
    """Base transcript fields."""

    model_name: str
    language: str
    language_probability: float | None
    text: str


class EnrichmentBase(BaseModel):
    """Base enrichment fields."""

    speaker_count: int | None
    talk_time_ratio: float | None
    silence_ratio: float | None
    segment_count: int | None


# Response schemas
class RecordingListItem(RecordingBase):
    """Recording item for list responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: RecordingStatus
    duration_sec: float | None
    created_at: datetime
    processed_at: datetime | None


class RecordingList(BaseModel):
    """Paginated list of recordings."""

    items: list[RecordingListItem]
    total: int
    page: int
    page_size: int
    has_more: bool


class TranscriptSegment(BaseModel):
    """A single transcript segment."""

    start: float
    end: float
    text: str
    speaker: str | None = None


class TranscriptDetail(TranscriptBase):
    """Full transcript with segments."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    beam_size: int | None
    compute_type: str | None
    segments: list[TranscriptSegment] = Field(default_factory=list)
    created_at: datetime


class EnrichmentDetail(EnrichmentBase):
    """Full enrichment details."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    diarization_enabled: bool
    total_speech_time: float | None
    total_silence_time: float | None
    avg_segment_length: float | None
    speaker_turns: int | None
    long_silence_count: int | None
    analytics_json: dict[str, Any] | None
    created_at: datetime


class RecordingDetail(RecordingBase):
    """Full recording details with transcript and enrichment."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: RecordingStatus
    error_message: str | None
    retry_count: int
    duration_sec: float | None
    sample_rate: int | None
    channels: int | None
    codec: str | None
    container: str | None
    bit_rate: int | None
    metadata_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None
    transcript: TranscriptDetail | None = None
    enrichment: EnrichmentDetail | None = None


# Request schemas
class IngestRequest(BaseModel):
    """Request to ingest files from a folder."""

    folder: str = Field(
        default=None,
        description="Folder path to scan. Defaults to CALLS_DIR.",
    )
    force_reprocess: bool = Field(
        default=False,
        description="Reprocess files even if already processed.",
    )


class IngestResponse(BaseModel):
    """Response from ingest operation."""

    discovered: int = Field(description="Number of new files discovered")
    queued: int = Field(description="Number of files queued for processing")
    skipped: int = Field(description="Number of files skipped (already processed)")
    errors: list[str] = Field(default_factory=list, description="Any errors encountered")


class ReprocessResponse(BaseModel):
    """Response from reprocess operation."""

    recording_id: UUID
    status: str
    message: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    database: str
    redis: str
    workers: int | None = None

