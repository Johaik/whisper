"""Tests for SQLAlchemy ORM models."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.db.models import Enrichment, Recording, RecordingStatus, Transcript


pytestmark = pytest.mark.db


class TestRecordingModel:
    """Tests for Recording model."""

    def test_create_recording(self, db_session: Session):
        """Test creating a basic recording."""
        recording = Recording(
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="abc123",
            file_size=1024,
            status=RecordingStatus.DISCOVERED,
        )
        db_session.add(recording)
        db_session.commit()

        assert recording.id is not None
        assert recording.created_at is not None
        assert recording.updated_at is not None

    def test_recording_default_status(self, db_session: Session):
        """Test that default status is DISCOVERED."""
        recording = Recording(
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="default123",
            file_size=1024,
        )
        db_session.add(recording)
        db_session.commit()

        assert recording.status == RecordingStatus.DISCOVERED

    def test_recording_with_metadata(self, db_session: Session):
        """Test recording with audio metadata fields."""
        recording = Recording(
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="meta123",
            file_size=2048000,
            duration_sec=120.5,
            sample_rate=44100,
            channels=2,
            codec="aac",
            container="m4a",
            bit_rate=128000,
            metadata_json={"extra": "data"},
        )
        db_session.add(recording)
        db_session.commit()
        db_session.refresh(recording)

        assert recording.duration_sec == 120.5
        assert recording.metadata_json == {"extra": "data"}

    def test_recording_processing_step_persisted(self, db_session: Session):
        """Test that processing_step and processing_step_started_at can be set and persisted."""
        started = datetime.now(timezone.utc)
        recording = Recording(
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="step123",
            file_size=1024,
            status=RecordingStatus.PROCESSING,
            processing_step="transcribe",
            processing_step_started_at=started,
            processing_segments_count=5,
        )
        db_session.add(recording)
        db_session.commit()
        db_session.refresh(recording)

        assert recording.processing_step == "transcribe"
        assert recording.processing_step_started_at is not None
        assert recording.processing_segments_count == 5

        # Clear and persist
        recording.processing_step = None
        recording.processing_step_started_at = None
        recording.processing_segments_count = None
        db_session.commit()
        db_session.refresh(recording)
        assert recording.processing_step is None
        assert recording.processing_step_started_at is None
        assert recording.processing_segments_count is None

    def test_recording_status_transitions(self, db_session: Session):
        """Test status field can be updated."""
        recording = Recording(
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="status123",
            file_size=1024,
            status=RecordingStatus.DISCOVERED,
        )
        db_session.add(recording)
        db_session.commit()

        # Transition through statuses
        recording.status = RecordingStatus.QUEUED
        db_session.commit()
        assert recording.status == RecordingStatus.QUEUED

        recording.status = RecordingStatus.PROCESSING
        db_session.commit()
        assert recording.status == RecordingStatus.PROCESSING

        recording.status = RecordingStatus.DONE
        db_session.commit()
        assert recording.status == RecordingStatus.DONE

    def test_recording_repr(self, db_session: Session):
        """Test recording string representation."""
        recording = Recording(
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="repr123",
            file_size=1024,
        )
        db_session.add(recording)
        db_session.commit()

        assert "test.m4a" in repr(recording)
        assert "discovered" in repr(recording)


class TestTranscriptModel:
    """Tests for Transcript model."""

    def test_create_transcript(self, db_session: Session, sample_recording: Recording):
        """Test creating a transcript."""
        transcript = Transcript(
            recording_id=sample_recording.id,
            model_name="test-model",
            language="he",
            language_probability=0.95,
            text="שלום עולם",
        )
        db_session.add(transcript)
        db_session.commit()

        assert transcript.id is not None
        assert transcript.created_at is not None

    def test_transcript_with_segments(self, db_session: Session, sample_recording: Recording):
        """Test transcript with segments JSON."""
        segments = [
            {"start": 0.0, "end": 2.0, "text": "שלום", "speaker": "SPEAKER_0"},
            {"start": 2.0, "end": 4.0, "text": "עולם", "speaker": "SPEAKER_1"},
        ]
        transcript = Transcript(
            recording_id=sample_recording.id,
            model_name="test-model",
            language="he",
            text="שלום עולם",
            segments_json=segments,
        )
        db_session.add(transcript)
        db_session.commit()
        db_session.refresh(transcript)

        assert len(transcript.segments_json) == 2
        assert transcript.segments_json[0]["speaker"] == "SPEAKER_0"

    def test_transcript_relationship(self, db_session: Session, sample_recording: Recording):
        """Test transcript-recording relationship."""
        transcript = Transcript(
            recording_id=sample_recording.id,
            model_name="test-model",
            language="he",
            text="Test",
        )
        db_session.add(transcript)
        db_session.commit()
        db_session.refresh(transcript)

        assert transcript.recording.id == sample_recording.id
        db_session.refresh(sample_recording)
        assert sample_recording.transcript.id == transcript.id


class TestEnrichmentModel:
    """Tests for Enrichment model."""

    def test_create_enrichment(self, db_session: Session, sample_recording: Recording):
        """Test creating an enrichment."""
        enrichment = Enrichment(
            recording_id=sample_recording.id,
            speaker_count=2,
            diarization_enabled=True,
            total_speech_time=45.0,
            total_silence_time=15.0,
            talk_time_ratio=0.75,
            silence_ratio=0.25,
        )
        db_session.add(enrichment)
        db_session.commit()

        assert enrichment.id is not None

    def test_enrichment_with_analytics_json(self, db_session: Session, sample_recording: Recording):
        """Test enrichment with analytics JSON."""
        analytics = {
            "speech_time_sec": 45.0,
            "silence_time_sec": 15.0,
            "segment_lengths": [10.0, 15.0, 20.0],
        }
        enrichment = Enrichment(
            recording_id=sample_recording.id,
            analytics_json=analytics,
        )
        db_session.add(enrichment)
        db_session.commit()
        db_session.refresh(enrichment)

        assert enrichment.analytics_json["speech_time_sec"] == 45.0

    def test_enrichment_relationship(self, db_session: Session, sample_recording: Recording):
        """Test enrichment-recording relationship."""
        enrichment = Enrichment(recording_id=sample_recording.id)
        db_session.add(enrichment)
        db_session.commit()
        db_session.refresh(enrichment)

        assert enrichment.recording.id == sample_recording.id
        db_session.refresh(sample_recording)
        assert sample_recording.enrichment.id == enrichment.id


class TestCascadeDelete:
    """Tests for cascade delete behavior."""

    def test_delete_recording_cascades_to_transcript(
        self, db_session: Session, processed_recording: Recording
    ):
        """Test that deleting recording deletes transcript."""
        recording_id = processed_recording.id

        db_session.delete(processed_recording)
        db_session.commit()

        transcript = db_session.query(Transcript).filter(
            Transcript.recording_id == recording_id
        ).first()
        assert transcript is None

    def test_delete_recording_cascades_to_enrichment(
        self, db_session: Session, processed_recording: Recording
    ):
        """Test that deleting recording deletes enrichment."""
        recording_id = processed_recording.id

        db_session.delete(processed_recording)
        db_session.commit()

        enrichment = db_session.query(Enrichment).filter(
            Enrichment.recording_id == recording_id
        ).first()
        assert enrichment is None

