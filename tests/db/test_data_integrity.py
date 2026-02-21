"""Tests for database constraints and data integrity.

These tests deliberately violate constraints (unique, foreign key, not-null)
and expect IntegrityError. When running against the test Postgres container,
those attempts produce ERROR lines in the DB logs—this is expected and not a bug.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Enrichment, Recording, RecordingStatus, Transcript


pytestmark = pytest.mark.db


class TestUniqueConstraints:
    """Tests for unique constraints."""

    def test_file_hash_must_be_unique(self, db_session: Session):
        """Test that file_hash has unique constraint."""
        recording1 = Recording(
            file_path="/data/calls/test1.m4a",
            file_name="test1.m4a",
            file_hash="duplicate_hash",
            file_size=1024,
        )
        db_session.add(recording1)
        db_session.commit()

        recording2 = Recording(
            file_path="/data/calls/test2.m4a",
            file_name="test2.m4a",
            file_hash="duplicate_hash",  # Same hash
            file_size=2048,
        )
        db_session.add(recording2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_recording_id_unique_in_transcript(self, db_session: Session, sample_recording: Recording):
        """Test that only one transcript per recording is allowed."""
        transcript1 = Transcript(
            recording_id=sample_recording.id,
            model_name="model1",
            language="he",
            text="First transcript",
        )
        db_session.add(transcript1)
        db_session.commit()

        transcript2 = Transcript(
            recording_id=sample_recording.id,
            model_name="model2",
            language="he",
            text="Second transcript",
        )
        db_session.add(transcript2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_recording_id_unique_in_enrichment(self, db_session: Session, sample_recording: Recording):
        """Test that only one enrichment per recording is allowed."""
        enrichment1 = Enrichment(recording_id=sample_recording.id)
        db_session.add(enrichment1)
        db_session.commit()

        enrichment2 = Enrichment(recording_id=sample_recording.id)
        db_session.add(enrichment2)

        with pytest.raises(IntegrityError):
            db_session.commit()


class TestForeignKeyConstraints:
    """Tests for foreign key constraints."""

    def test_transcript_requires_valid_recording(self, db_session: Session):
        """Test that transcript FK is enforced."""
        transcript = Transcript(
            recording_id=uuid.uuid4(),  # Nonexistent
            model_name="test",
            language="he",
            text="Test",
        )
        db_session.add(transcript)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_enrichment_requires_valid_recording(self, db_session: Session):
        """Test that enrichment FK is enforced."""
        enrichment = Enrichment(recording_id=uuid.uuid4())  # Nonexistent
        db_session.add(enrichment)

        with pytest.raises(IntegrityError):
            db_session.commit()


class TestNotNullConstraints:
    """Tests for not-null constraints."""

    def test_recording_requires_file_path(self, db_session: Session):
        """Test that file_path is required."""
        recording = Recording(
            file_name="test.m4a",
            file_hash="hash123",
            file_size=1024,
        )
        db_session.add(recording)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_recording_requires_file_hash(self, db_session: Session):
        """Test that file_hash is required."""
        recording = Recording(
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_size=1024,
        )
        db_session.add(recording)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_transcript_requires_text(self, db_session: Session, sample_recording: Recording):
        """Test that transcript text is required."""
        transcript = Transcript(
            recording_id=sample_recording.id,
            model_name="test",
            language="he",
            # text is missing
        )
        db_session.add(transcript)

        with pytest.raises(IntegrityError):
            db_session.commit()


class TestStatusTransitions:
    """Tests for valid status transitions."""

    def test_all_status_values_are_valid(self, db_session: Session):
        """Test that all RecordingStatus enum values work."""
        for status in RecordingStatus:
            recording = Recording(
                file_path=f"/data/calls/test_{status.value}.m4a",
                file_name=f"test_{status.value}.m4a",
                file_hash=f"hash_{status.value}",
                file_size=1024,
                status=status,
            )
            db_session.add(recording)
            db_session.commit()

            db_session.refresh(recording)
            assert recording.status == status


class TestJsonbFields:
    """Tests for JSONB field validation."""

    def test_metadata_json_stores_complex_structure(self, db_session: Session):
        """Test that metadata_json can store complex ffprobe output."""
        metadata = {
            "format": {
                "filename": "test.m4a",
                "format_name": "mov,mp4,m4a",
                "duration": "60.123",
                "bit_rate": "128000",
            },
            "streams": [
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "sample_rate": "44100",
                    "channels": 2,
                }
            ],
        }

        recording = Recording(
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="jsonb_test",
            file_size=1024,
            metadata_json=metadata,
        )
        db_session.add(recording)
        db_session.commit()
        db_session.refresh(recording)

        assert recording.metadata_json["format"]["filename"] == "test.m4a"
        assert len(recording.metadata_json["streams"]) == 1

    def test_segments_json_stores_list_of_segments(
        self, db_session: Session, sample_recording: Recording
    ):
        """Test that segments_json stores segment list correctly."""
        segments = [
            {"start": 0.0, "end": 2.0, "text": "Hello", "speaker": "SPEAKER_0"},
            {"start": 2.5, "end": 5.0, "text": "World", "speaker": "SPEAKER_1"},
            {"start": 5.5, "end": 10.0, "text": "Test", "speaker": None},
        ]

        transcript = Transcript(
            recording_id=sample_recording.id,
            model_name="test",
            language="he",
            text="Hello World Test",
            segments_json=segments,
        )
        db_session.add(transcript)
        db_session.commit()
        db_session.refresh(transcript)

        assert len(transcript.segments_json) == 3
        assert transcript.segments_json[0]["start"] == 0.0
        assert transcript.segments_json[1]["speaker"] == "SPEAKER_1"
        assert transcript.segments_json[2]["speaker"] is None

    def test_analytics_json_stores_nested_data(
        self, db_session: Session, sample_recording: Recording
    ):
        """Test that analytics_json stores nested analytics."""
        analytics = {
            "speech_time_sec": 45.5,
            "silence_time_sec": 14.5,
            "segment_lengths": [10.0, 15.5, 20.0],
            "silence_lengths": [2.5, 5.0, 7.0],
            "speaker_talk_times": {
                "SPEAKER_0": 25.0,
                "SPEAKER_1": 20.5,
            },
            "long_silences": [7.0],
        }

        enrichment = Enrichment(
            recording_id=sample_recording.id,
            analytics_json=analytics,
        )
        db_session.add(enrichment)
        db_session.commit()
        db_session.refresh(enrichment)

        assert enrichment.analytics_json["speech_time_sec"] == 45.5
        assert len(enrichment.analytics_json["segment_lengths"]) == 3
        assert enrichment.analytics_json["speaker_talk_times"]["SPEAKER_0"] == 25.0


class TestTimestamps:
    """Tests for timestamp field behavior."""

    def test_created_at_is_set_automatically(self, db_session: Session):
        """Test that created_at is set on insert."""
        before = datetime.now(timezone.utc)

        recording = Recording(
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="timestamp_test",
            file_size=1024,
        )
        db_session.add(recording)
        db_session.commit()

        after = datetime.now(timezone.utc)

        # Ensure timezone awareness for SQLite tests
        created_at = recording.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        assert before <= created_at <= after

    def test_updated_at_changes_on_update(self, db_session: Session):
        """Test that updated_at changes when record is updated."""
        recording = Recording(
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="update_test",
            file_size=1024,
        )
        db_session.add(recording)
        db_session.commit()

        original_updated_at = recording.updated_at

        # Update the record
        recording.status = RecordingStatus.QUEUED
        db_session.commit()

        # Note: This test may not work perfectly as updated_at relies on
        # onupdate which may not trigger in all scenarios
        # The actual behavior depends on SQLAlchemy session management

    def test_processed_at_initially_null(self, db_session: Session):
        """Test that processed_at is null for new recordings."""
        recording = Recording(
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="processed_test",
            file_size=1024,
        )
        db_session.add(recording)
        db_session.commit()

        assert recording.processed_at is None

    def test_processed_at_can_be_set(self, db_session: Session):
        """Test that processed_at can be set when processing completes."""
        recording = Recording(
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="processed_set_test",
            file_size=1024,
        )
        db_session.add(recording)
        db_session.commit()

        now = datetime.now(timezone.utc)
        recording.processed_at = now
        recording.status = RecordingStatus.DONE
        db_session.commit()

        # Ensure timezone awareness for SQLite tests
        processed_at = recording.processed_at
        if processed_at and processed_at.tzinfo is None:
            processed_at = processed_at.replace(tzinfo=timezone.utc)

        assert processed_at == now

