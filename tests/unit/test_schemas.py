"""Unit tests for API response schemas."""

import uuid
from datetime import datetime

import pytest

from app.api.schemas import RecordingDetail, RecordingListItem
from app.db.models import RecordingStatus


@pytest.mark.unit
class TestRecordingSchemasSegmentProgress:
    """Tests that recording schemas include processing_segments_count."""

    def test_recording_list_item_has_processing_segments_count(self):
        """RecordingListItem includes processing_segments_count (null by default)."""
        item = RecordingListItem(
            id=uuid.uuid4(),
            file_path="/data/calls/t.m4a",
            file_name="t.m4a",
            file_hash="h",
            file_size=1000,
            status=RecordingStatus.DONE,
            duration_sec=60.0,
            created_at=datetime.utcnow(),
            processed_at=datetime.utcnow(),
        )
        assert hasattr(item, "processing_segments_count")
        assert item.processing_segments_count is None

    def test_recording_list_item_accepts_processing_segments_count(self):
        """RecordingListItem accepts processing_segments_count when set."""
        item = RecordingListItem(
            id=uuid.uuid4(),
            file_path="/data/calls/t.m4a",
            file_name="t.m4a",
            file_hash="h",
            file_size=1000,
            status=RecordingStatus.PROCESSING,
            duration_sec=None,
            created_at=datetime.utcnow(),
            processed_at=None,
            processing_segments_count=7,
        )
        assert item.processing_segments_count == 7

    def test_recording_detail_has_processing_segments_count(self):
        """RecordingDetail includes processing_segments_count."""
        detail = RecordingDetail(
            id=uuid.uuid4(),
            file_path="/data/calls/t.m4a",
            file_name="t.m4a",
            file_hash="h",
            file_size=1000,
            status=RecordingStatus.PROCESSING,
            error_message=None,
            retry_count=0,
            duration_sec=60.0,
            sample_rate=None,
            channels=None,
            codec=None,
            container=None,
            bit_rate=None,
            metadata_json=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            processed_at=None,
            transcript=None,
            enrichment=None,
            processing_segments_count=3,
        )
        assert detail.processing_segments_count == 3

    def test_recording_list_item_has_processing_step_fields(self):
        """RecordingListItem includes processing_step and processing_step_started_at (null by default)."""
        item = RecordingListItem(
            id=uuid.uuid4(),
            file_path="/data/calls/t.m4a",
            file_name="t.m4a",
            file_hash="h",
            file_size=1000,
            status=RecordingStatus.DONE,
            duration_sec=60.0,
            created_at=datetime.utcnow(),
            processed_at=datetime.utcnow(),
        )
        assert hasattr(item, "processing_step")
        assert item.processing_step is None
        assert hasattr(item, "processing_step_started_at")
        assert item.processing_step_started_at is None

    def test_recording_list_item_accepts_processing_step_when_set(self):
        """RecordingListItem accepts processing_step and processing_step_started_at when set."""
        now = datetime.utcnow()
        item = RecordingListItem(
            id=uuid.uuid4(),
            file_path="/data/calls/t.m4a",
            file_name="t.m4a",
            file_hash="h",
            file_size=1000,
            status=RecordingStatus.PROCESSING,
            duration_sec=None,
            created_at=datetime.utcnow(),
            processed_at=None,
            processing_segments_count=5,
            processing_step="transcribe",
            processing_step_started_at=now,
        )
        assert item.processing_step == "transcribe"
        assert item.processing_step_started_at == now

    def test_recording_detail_has_processing_step_fields(self):
        """RecordingDetail includes processing_step and processing_step_started_at."""
        now = datetime.utcnow()
        detail = RecordingDetail(
            id=uuid.uuid4(),
            file_path="/data/calls/t.m4a",
            file_name="t.m4a",
            file_hash="h",
            file_size=1000,
            status=RecordingStatus.PROCESSING,
            error_message=None,
            retry_count=0,
            processing_segments_count=10,
            processing_step="diarization",
            processing_step_started_at=now,
            duration_sec=60.0,
            sample_rate=None,
            channels=None,
            codec=None,
            container=None,
            bit_rate=None,
            metadata_json=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            processed_at=None,
            transcript=None,
            enrichment=None,
        )
        assert detail.processing_step == "diarization"
        assert detail.processing_step_started_at == now
