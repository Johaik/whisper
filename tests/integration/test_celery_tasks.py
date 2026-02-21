"""Integration tests for Celery tasks."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import _test_db_reachable, get_test_settings, USE_SQLITE
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.models import Base, Enrichment, Recording, RecordingStatus, Transcript
from app.processors.analytics import AnalyticsResult
from app.processors.diarize import DiarizationResult
from app.processors.metadata import AudioMetadata
from app.processors.transcribe import TranscriptionResult, TranscriptSegment
from app.worker.tasks import enqueue_pending_recordings, process_recording


pytestmark = pytest.mark.integration


class TestProcessRecordingTask:
    """Tests for the process_recording Celery task."""

    @pytest.fixture
    def task_db_engine(self):
        """Create a database engine for celery task tests."""
        if not _test_db_reachable():
            pytest.skip("Test Postgres not reachable at localhost:5433 (start test DB or skip)")
        settings = get_test_settings()

        connect_args = {}
        if USE_SQLITE:
            connect_args = {"check_same_thread": False}

        engine = create_engine(
            settings.database_url_sync,
            connect_args=connect_args
        )

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

        # Verify error message was stored (includes step for diagnosis)
        verify_session = task_session_factory()
        recording = verify_session.query(Recording).filter(Recording.id == recording_id).first()
        assert "extract_metadata" in (recording.error_message or "")
        assert "ffprobe failed" in (recording.error_message or "")
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
        assert rec.processing_step is None
        assert rec.processing_step_started_at is None
        verify_session.close()

    def test_process_recording_error_message_includes_step_on_transcribe_failure(
        self, task_session_factory, mock_processors
    ):
        """Test that when transcribe fails, error_message includes step and segment count."""
        setup_session = task_session_factory()
        recording = Recording(
            id=uuid.uuid4(),
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="transcribeerrhash",
            file_size=768000,
            status=RecordingStatus.QUEUED,
        )
        setup_session.add(recording)
        setup_session.commit()
        recording_id = recording.id
        setup_session.close()

        def mock_get_session():
            return task_session_factory()

        def transcribe_side_effect(*args, **kwargs):
            progress_cb = kwargs.get("progress_callback")
            if progress_cb:
                progress_cb(5)  # simulate 5 segments before failure
            raise RuntimeError("Whisper model error")

        mock_processors["transcribe"].side_effect = transcribe_side_effect

        with patch("app.worker.tasks.get_sync_session", mock_get_session):
            with patch("app.worker.tasks.get_settings") as mock_settings:
                mock_settings.return_value = get_test_settings()
                with pytest.raises(RuntimeError):
                    process_recording(str(recording_id))

        verify_session = task_session_factory()
        rec = verify_session.query(Recording).filter(Recording.id == recording_id).first()
        assert "transcribe" in (rec.error_message or "")
        assert "5 segments" in (rec.error_message or "")
        assert "Whisper model error" in (rec.error_message or "")
        verify_session.close()

    def test_process_recording_continues_on_diarization_failure(
        self, task_session_factory, mock_processors
    ):
        """Test that processing continues even if diarization fails."""
        # Create recording
        setup_session = task_session_factory()
        recording = Recording(
            id=uuid.uuid4(),
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="diarizefailhash",
            file_size=768000,
            status=RecordingStatus.QUEUED,
        )
        setup_session.add(recording)
        setup_session.commit()
        recording_id = recording.id
        setup_session.close()

        # Mock diarization to fail
        mock_processors["diarize"].side_effect = Exception("Diarization service unavailable")

        def mock_get_session():
            return task_session_factory()

        # Create settings with diarization enabled
        diarize_settings = get_test_settings()
        diarize_settings.diarization_enabled = True

        with patch("app.worker.tasks.get_sync_session", mock_get_session):
            with patch("app.worker.tasks.get_settings") as mock_settings:
                mock_settings.return_value = diarize_settings
                result = process_recording(str(recording_id))

        # Verify task success
        assert result["status"] == "success"

        # Verify recording status is DONE
        verify_session = task_session_factory()
        rec = verify_session.query(Recording).filter(Recording.id == recording_id).first()
        assert rec.status == RecordingStatus.DONE
        assert rec.error_message is None

        # Verify enrichment shows diarization disabled (due to failure)
        enrichment = verify_session.query(Enrichment).filter(
            Enrichment.recording_id == recording_id
        ).first()
        assert enrichment is not None
        assert enrichment.diarization_enabled is False

        verify_session.close()


class TestEnqueuePendingRecordings:
    """Tests for the enqueue_pending_recordings (beat) task."""

    @pytest.fixture
    def beat_db_engine(self):
        """Create a database engine for beat task tests."""
        if not _test_db_reachable():
            pytest.skip("Test Postgres not reachable at localhost:5433 (start test DB or skip)")
        settings = get_test_settings()

        connect_args = {}
        if USE_SQLITE:
            connect_args = {"check_same_thread": False}

        engine = create_engine(
            settings.database_url_sync,
            connect_args=connect_args
        )

        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        yield engine
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

    @pytest.fixture
    def beat_session_factory(self, beat_db_engine):
        return sessionmaker(bind=beat_db_engine)

    def test_stuck_recording_marked_failed_with_step_in_error_message(
        self, beat_session_factory
    ):
        """When a stuck PROCESSING recording is at max retries, error_message includes step and segments."""
        from app.config import get_settings

        session = beat_session_factory()
        settings = get_settings()
        stuck_threshold = settings.stuck_processing_threshold_sec
        # Create a recording that will be considered stuck (updated_at in the past)
        rec = Recording(
            id=uuid.uuid4(),
            file_path="/data/calls/stuck.m4a",
            file_name="stuck.m4a",
            file_hash="stuckhash",
            file_size=1000,
            status=RecordingStatus.PROCESSING,
            processing_step="transcribe",
            processing_segments_count=30,
            retry_count=settings.task_max_retries - 1,  # one more stuck run will mark failed
            updated_at=datetime.now(timezone.utc)
            - timedelta(seconds=stuck_threshold + 60),
        )
        session.add(rec)
        session.commit()
        recording_id = rec.id
        session.close()

        def mock_get_session():
            return beat_session_factory()

        with patch("app.worker.tasks.get_sync_session", mock_get_session):
            with patch("app.worker.tasks.get_settings") as mock_settings:
                mock_settings.return_value = get_test_settings()
                enqueue_pending_recordings()

        verify = beat_session_factory()
        r = verify.query(Recording).filter(Recording.id == recording_id).first()
        assert r.status == RecordingStatus.FAILED
        assert "transcribe" in (r.error_message or "")
        assert "30 segments" in (r.error_message or "")
        assert "cleanup" in (r.error_message or "")
        verify.close()

    def test_stuck_recording_logged_with_step_and_segments(
        self, beat_session_factory, caplog
    ):
        """Beat task logs stuck recordings with file, step, segments, age_sec."""
        from app.config import get_settings

        session = beat_session_factory()
        settings = get_settings()
        stuck_threshold = settings.stuck_processing_threshold_sec
        rec = Recording(
            id=uuid.uuid4(),
            file_path="/data/calls/logged.m4a",
            file_name="logged.m4a",
            file_hash="loggedhash",
            file_size=1000,
            status=RecordingStatus.PROCESSING,
            processing_step="diarization",
            processing_segments_count=0,
            retry_count=settings.task_max_retries - 1,
            updated_at=datetime.now(timezone.utc)
            - timedelta(seconds=stuck_threshold + 300),
        )
        session.add(rec)
        session.commit()
        session.close()

        with patch("app.worker.tasks.get_sync_session", lambda: beat_session_factory()):
            with patch("app.worker.tasks.get_settings") as mock_settings:
                mock_settings.return_value = get_test_settings()
                # Mock Celery control.inspect to avoid flakiness with real Redis
                with patch("app.worker.tasks.celery_app.control.inspect") as mock_inspect:
                    mock_inspect.return_value.active.return_value = None
                    # Use mock logger for 100% reliability in full test suite
                    with patch("app.worker.tasks.logger") as mock_logger:
                        enqueue_pending_recordings()

                        # Verify stuck log (check any call contains the expected parts)
                        stuck_calls = [call for call in mock_logger.warning.call_args_list if "Stuck recording" in str(call)]
                        assert len(stuck_calls) > 0, f"Stuck log missing. Calls: {mock_logger.warning.call_args_list}"
                        call_msg = str(stuck_calls[0])
                        assert "logged.m4a" in call_msg
                        assert "diarization" in call_msg

    def test_processing_not_stuck_when_updated_at_recent(self, beat_session_factory):
        """PROCESSING recording with recent updated_at is not reset."""
        session = beat_session_factory()
        rec = Recording(
            id=uuid.uuid4(),
            file_path="/data/calls/recent.m4a",
            file_name="recent.m4a",
            file_hash="recenthash",
            file_size=1000,
            status=RecordingStatus.PROCESSING,
            processing_step="transcribe",
            updated_at=datetime.now(timezone.utc),  # just now
        )
        session.add(rec)
        session.commit()
        recording_id = rec.id
        session.close()

        with patch("app.worker.tasks.get_sync_session", lambda: beat_session_factory()):
            with patch("app.worker.tasks.get_settings") as mock_settings:
                mock_settings.return_value = get_test_settings()
                enqueue_pending_recordings()

        verify = beat_session_factory()
        r = verify.query(Recording).filter(Recording.id == recording_id).first()
        assert r.status == RecordingStatus.PROCESSING
        verify.close()
