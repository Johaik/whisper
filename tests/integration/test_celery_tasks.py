"""Integration tests for Celery tasks."""

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.models import Base, Enrichment, Recording, RecordingStatus, Transcript
from app.processors.analytics import AnalyticsResult
from app.processors.diarize import DiarizationResult
from app.processors.metadata import AudioMetadata
from app.processors.transcribe import TranscriptionResult, TranscriptSegment
from app.worker.tasks import process_recording


pytestmark = pytest.mark.integration


def get_test_settings() -> Settings:
    """Get test-specific settings."""
    return Settings(
        api_token="test-token",
        database_url="postgresql+asyncpg://whisper_test:whisper_test@localhost:5433/whisper_test",
        database_url_sync="postgresql://whisper_test:whisper_test@localhost:5433/whisper_test",
        redis_url="redis://localhost:6380/0",
        calls_dir="/tmp/test_calls",
        output_dir="/tmp/whisper_test_outputs",
        diarization_enabled=False,
    )


class TestProcessRecordingTask:
    """Tests for the process_recording Celery task."""

    @pytest.fixture
    def task_db_engine(self):
        """Create a database engine for celery task tests."""
        settings = get_test_settings()
        engine = create_engine(settings.database_url_sync)

        # Create fresh tables
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        yield engine

        # Cleanup
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

    @pytest.fixture
    def task_session_factory(self, task_db_engine):
        """Create a session factory for tests."""
        return sessionmaker(bind=task_db_engine)

    @pytest.fixture
    def mock_processors(self):
        """Mock all processor functions."""
        with patch("app.worker.tasks.extract_metadata") as mock_metadata, \
             patch("app.worker.tasks.transcribe_audio") as mock_transcribe, \
             patch("app.worker.tasks.diarize_audio") as mock_diarize, \
             patch("app.worker.tasks.compute_analytics") as mock_analytics:

            # Setup metadata mock
            mock_metadata.return_value = AudioMetadata(
                duration_sec=60.0,
                sample_rate=44100,
                channels=2,
                codec="aac",
                container="m4a",
                bit_rate=128000,
                file_size=768000,
                file_hash="testhash",
                raw_metadata={"format": {}, "streams": []},
            )

            # Setup transcription mock
            mock_transcribe.return_value = TranscriptionResult(
                text="שלום עולם",
                segments=[
                    TranscriptSegment(start=0.0, end=2.0, text="שלום"),
                    TranscriptSegment(start=2.0, end=4.0, text="עולם"),
                ],
                language="he",
                language_probability=0.95,
                model_name="test-model",
                beam_size=5,
                compute_type="int8",
            )

            # Setup diarization mock
            mock_diarize.return_value = DiarizationResult(
                segments=[],
                speaker_count=0,
                speakers=[],
            )

            # Setup analytics mock
            mock_analytics.return_value = AnalyticsResult(
                total_speech_time=4.0,
                total_silence_time=56.0,
                talk_time_ratio=0.067,
                silence_ratio=0.933,
                segment_count=2,
                avg_segment_length=2.0,
                speaker_count=0,
                speaker_turns=0,
                long_silence_count=1,
                long_silence_threshold_sec=5.0,
                speaker_talk_times={},
                analytics_json={},
            )

            yield {
                "metadata": mock_metadata,
                "transcribe": mock_transcribe,
                "diarize": mock_diarize,
                "analytics": mock_analytics,
            }

    def test_process_recording_success(self, task_session_factory, mock_processors):
        """Test successful recording processing."""
        # Create a recording using setup session
        setup_session = task_session_factory()
        recording = Recording(
            id=uuid.uuid4(),
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="taskhash123",
            file_size=768000,
            status=RecordingStatus.QUEUED,
        )
        setup_session.add(recording)
        setup_session.commit()
        recording_id = recording.id
        setup_session.close()

        # Mock get_sync_session to return new session from our factory
        def mock_get_session():
            return task_session_factory()

        # Process the recording
        with patch("app.worker.tasks.get_sync_session", mock_get_session):
            with patch("app.worker.tasks.get_settings") as mock_settings:
                mock_settings.return_value = get_test_settings()
                result = process_recording(str(recording_id))

        assert result["status"] == "success"
        assert result["segments"] == 2

        # Verify with a fresh session
        verify_session = task_session_factory()
        recording = verify_session.query(Recording).filter(Recording.id == recording_id).first()
        assert recording.status == RecordingStatus.DONE
        assert recording.duration_sec == 60.0
        assert recording.processed_at is not None
        assert recording.processing_segments_count is None

        # Verify transcript was created
        transcript = verify_session.query(Transcript).filter(
            Transcript.recording_id == recording_id
        ).first()
        assert transcript is not None
        assert transcript.text == "שלום עולם"
        assert transcript.language == "he"

        # Verify enrichment was created
        enrichment = verify_session.query(Enrichment).filter(
            Enrichment.recording_id == recording_id
        ).first()
        assert enrichment is not None
        assert enrichment.segment_count == 2

        verify_session.close()

    def test_process_recording_not_found(self, task_session_factory):
        """Test processing nonexistent recording."""
        def mock_get_session():
            return task_session_factory()

        with patch("app.worker.tasks.get_sync_session", mock_get_session):
            result = process_recording(str(uuid.uuid4()))

        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_process_recording_updates_status_to_processing(
        self, task_session_factory, mock_processors
    ):
        """Test that status is updated to PROCESSING during execution."""
        # Create recording
        setup_session = task_session_factory()
        recording = Recording(
            id=uuid.uuid4(),
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="statushash",
            file_size=768000,
            status=RecordingStatus.QUEUED,
        )
        setup_session.add(recording)
        setup_session.commit()
        recording_id = recording.id
        setup_session.close()

        processing_status_seen = []

        # Check status during processing
        original_transcribe = mock_processors["transcribe"].return_value

        def check_status_during_transcribe(*args, **kwargs):
            check_session = task_session_factory()
            rec = check_session.query(Recording).filter(Recording.id == recording_id).first()
            processing_status_seen.append(rec.status)
            check_session.close()
            return original_transcribe

        mock_processors["transcribe"].side_effect = check_status_during_transcribe

        def mock_get_session():
            return task_session_factory()

        with patch("app.worker.tasks.get_sync_session", mock_get_session):
            with patch("app.worker.tasks.get_settings") as mock_settings:
                mock_settings.return_value = get_test_settings()
                process_recording(str(recording_id))

        assert RecordingStatus.PROCESSING in processing_status_seen

    def test_process_recording_handles_metadata_error(self, task_session_factory):
        """Test handling of metadata extraction error."""
        # Create recording
        setup_session = task_session_factory()
        recording = Recording(
            id=uuid.uuid4(),
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="errorhash",
            file_size=768000,
            status=RecordingStatus.QUEUED,
        )
        setup_session.add(recording)
        setup_session.commit()
        recording_id = recording.id
        setup_session.close()

        def mock_get_session():
            return task_session_factory()

        with patch("app.worker.tasks.extract_metadata") as mock_metadata:
            mock_metadata.side_effect = RuntimeError("ffprobe failed")

            with patch("app.worker.tasks.get_sync_session", mock_get_session):
                with patch("app.worker.tasks.get_settings") as mock_settings:
                    mock_settings.return_value = get_test_settings()
                    with pytest.raises(RuntimeError):
                        process_recording(str(recording_id))

        # Verify error message was stored
        verify_session = task_session_factory()
        recording = verify_session.query(Recording).filter(Recording.id == recording_id).first()
        assert recording.error_message == "ffprobe failed"
        verify_session.close()

    def test_process_recording_with_diarization(self, task_session_factory, mock_processors):
        """Test processing with diarization enabled."""
        from app.processors.diarize import DiarizationSegment

        # Update diarization mock
        mock_processors["diarize"].return_value = DiarizationResult(
            segments=[
                DiarizationSegment(start=0.0, end=2.0, speaker="SPEAKER_0"),
                DiarizationSegment(start=2.0, end=4.0, speaker="SPEAKER_1"),
            ],
            speaker_count=2,
            speakers=["SPEAKER_0", "SPEAKER_1"],
        )

        mock_processors["analytics"].return_value.speaker_count = 2

        # Create recording
        setup_session = task_session_factory()
        recording = Recording(
            id=uuid.uuid4(),
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="diarizehash",
            file_size=768000,
            status=RecordingStatus.QUEUED,
        )
        setup_session.add(recording)
        setup_session.commit()
        recording_id = recording.id
        setup_session.close()

        def mock_get_session():
            return task_session_factory()

        # Create settings with diarization enabled
        diarize_settings = get_test_settings()
        diarize_settings.diarization_enabled = True

        with patch("app.worker.tasks.get_sync_session", mock_get_session):
            with patch("app.worker.tasks.get_settings") as mock_settings:
                mock_settings.return_value = diarize_settings
                result = process_recording(str(recording_id))

        assert result["speakers"] == 2

        # Verify enrichment has speaker info
        verify_session = task_session_factory()
        enrichment = verify_session.query(Enrichment).filter(
            Enrichment.recording_id == recording_id
        ).first()
        assert enrichment.diarization_enabled is True
        verify_session.close()

    def test_process_recording_reprocessing(self, task_session_factory, mock_processors):
        """Test reprocessing an already processed recording."""
        # Create recording
        setup_session = task_session_factory()
        recording = Recording(
            id=uuid.uuid4(),
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="reprocesshash2",
            file_size=768000,
            status=RecordingStatus.QUEUED,
        )
        setup_session.add(recording)
        setup_session.commit()
        recording_id = recording.id
        setup_session.close()

        def mock_get_session():
            return task_session_factory()

        # Process first time
        with patch("app.worker.tasks.get_sync_session", mock_get_session):
            with patch("app.worker.tasks.get_settings") as mock_settings:
                mock_settings.return_value = get_test_settings()
                process_recording(str(recording_id))

        # Update transcription result for second run
        mock_processors["transcribe"].return_value = TranscriptionResult(
            text="טקסט מעודכן",
            segments=[TranscriptSegment(start=0.0, end=5.0, text="טקסט מעודכן")],
            language="he",
            language_probability=0.99,
            model_name="test-model-v2",
            beam_size=10,
            compute_type="float16",
        )

        # Reset status for reprocessing
        reprocess_session = task_session_factory()
        recording = reprocess_session.query(Recording).filter(Recording.id == recording_id).first()
        recording.status = RecordingStatus.QUEUED
        reprocess_session.commit()
        reprocess_session.close()

        # Reprocess
        with patch("app.worker.tasks.get_sync_session", mock_get_session):
            with patch("app.worker.tasks.get_settings") as mock_settings:
                mock_settings.return_value = get_test_settings()
                process_recording(str(recording_id))

        # Verify transcript was updated (not duplicated)
        verify_session = task_session_factory()
        transcripts = verify_session.query(Transcript).filter(
            Transcript.recording_id == recording_id
        ).all()
        assert len(transcripts) == 1
        assert transcripts[0].text == "טקסט מעודכן"
        verify_session.close()

    def test_process_recording_passes_progress_callback_to_transcribe(
        self, task_session_factory, mock_processors
    ):
        """Test that transcribe_audio is called with a progress_callback."""
        setup_session = task_session_factory()
        recording = Recording(
            id=uuid.uuid4(),
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="progresshash",
            file_size=768000,
            status=RecordingStatus.QUEUED,
        )
        setup_session.add(recording)
        setup_session.commit()
        recording_id = recording.id
        setup_session.close()

        def mock_get_session():
            return task_session_factory()

        with patch("app.worker.tasks.get_sync_session", mock_get_session):
            with patch("app.worker.tasks.get_settings") as mock_settings:
                mock_settings.return_value = get_test_settings()
                process_recording(str(recording_id))

        mock_transcribe = mock_processors["transcribe"]
        mock_transcribe.assert_called_once()
        call_kwargs = mock_transcribe.call_args[1]
        assert "progress_callback" in call_kwargs
        assert callable(call_kwargs["progress_callback"])

    def test_process_recording_clears_segment_progress_on_success(
        self, task_session_factory, mock_processors
    ):
        """Test that processing_segments_count is cleared after successful processing."""
        setup_session = task_session_factory()
        recording = Recording(
            id=uuid.uuid4(),
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="clearprogresshash",
            file_size=768000,
            status=RecordingStatus.QUEUED,
        )
        setup_session.add(recording)
        setup_session.commit()
        recording_id = recording.id
        setup_session.close()

        def mock_get_session():
            return task_session_factory()

        with patch("app.worker.tasks.get_sync_session", mock_get_session):
            with patch("app.worker.tasks.get_settings") as mock_settings:
                mock_settings.return_value = get_test_settings()
                process_recording(str(recording_id))

        verify_session = task_session_factory()
        rec = verify_session.query(Recording).filter(Recording.id == recording_id).first()
        assert rec.status == RecordingStatus.DONE
        assert rec.processing_segments_count is None
        verify_session.close()
