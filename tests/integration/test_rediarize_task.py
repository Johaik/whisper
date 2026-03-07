"""Integration tests for the re-diarization tasks."""

import uuid
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests.conftest import _test_db_reachable, get_test_settings, USE_SQLITE
from app.db.models import Base, Enrichment, Recording, RecordingStatus, Transcript
from app.processors.analytics import AnalyticsResult
from app.processors.diarize import DiarizationResult, DiarizationSegment
from app.worker.tasks import rediarize_recording, enqueue_rediarization_tasks, TranscriptSegment

pytestmark = pytest.mark.integration

class TestRediarizeTask:
    """Tests for the rediarize_recording Celery task."""

    @pytest.fixture
    def task_db_engine(self):
        """Create a database engine for tests."""
        if not _test_db_reachable():
            pytest.skip("Test Postgres not reachable")
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
    def task_session_factory(self, task_db_engine):
        return sessionmaker(bind=task_db_engine)

    @pytest.fixture
    def mock_processors(self):
        """Mock diarization and analytics."""
        with patch("app.worker.tasks.diarize_audio") as mock_diarize, \
             patch("app.worker.tasks._compute_analytics_step") as mock_analytics, \
             patch("os.path.exists") as mock_exists:

            mock_exists.return_value = True

            mock_diarize.return_value = DiarizationResult(
                segments=[
                    DiarizationSegment(start=0.0, end=2.0, speaker="SPEAKER_0"),
                    DiarizationSegment(start=2.0, end=4.0, speaker="SPEAKER_1"),
                ],
                speaker_count=2,
                speakers=["SPEAKER_0", "SPEAKER_1"],
            )

            mock_analytics.return_value = AnalyticsResult(
                total_speech_time=4.0,
                total_silence_time=56.0,
                talk_time_ratio=0.067,
                silence_ratio=0.933,
                segment_count=2,
                avg_segment_length=2.0,
                speaker_count=2,
                speaker_turns=2,
                long_silence_count=1,
                long_silence_threshold_sec=5.0,
                speaker_talk_times={"SPEAKER_0": 2.0, "SPEAKER_1": 2.0},
                analytics_json={"test": "data"},
            )

            yield {
                "diarize": mock_diarize,
                "analytics": mock_analytics,
            }

    def test_rediarize_recording_success(self, task_session_factory, mock_processors):
        """Test successful re-diarization of a recording."""
        setup_session = task_session_factory()
        
        recording_id = uuid.uuid4()
        recording = Recording(
            id=recording_id,
            file_path="/data/calls/test.m4a",
            file_name="test.m4a",
            file_hash="hash1",
            file_size=1000,
            status=RecordingStatus.DONE,
            duration_sec=60.0,
        )
        setup_session.add(recording)
        
        transcript = Transcript(
            recording_id=recording_id,
            model_name="test",
            language="he",
            text="hello world",
            segments_json=[
                {"start": 0.0, "end": 2.0, "text": "hello"},
                {"start": 2.0, "end": 4.0, "text": "world"},
            ]
        )
        setup_session.add(transcript)
        
        enrichment = Enrichment(
            recording_id=recording_id,
            diarization_enabled=False,
            diarization_pending=True,
            speaker_count=0
        )
        setup_session.add(enrichment)
        
        setup_session.commit()
        setup_session.close()

        def mock_get_session():
            return task_session_factory()

        with patch("app.worker.tasks.get_sync_session", mock_get_session):
            with patch("app.worker.tasks.get_settings") as mock_settings:
                mock_settings.return_value = get_test_settings()
                result = rediarize_recording(str(recording_id))

        assert result["status"] == "success"
        assert result["speakers"] == 2

        # Verify database updates
        verify_session = task_session_factory()
        enr = verify_session.query(Enrichment).filter(Enrichment.recording_id == recording_id).first()
        assert enr.diarization_enabled is True
        assert enr.diarization_pending is False
        assert enr.speaker_count == 2
        
        tr = verify_session.query(Transcript).filter(Transcript.recording_id == recording_id).first()
        assert tr.segments_json[0]["speaker"] == "SPEAKER_0"
        assert tr.segments_json[1]["speaker"] == "SPEAKER_1"
        
        verify_session.close()

    def test_rediarize_recording_with_num_speakers(self, task_session_factory, mock_processors):
        """Test re-diarization with explicit num_speakers."""
        setup_session = task_session_factory()
        
        recording_id = uuid.uuid4()
        recording = Recording(
            id=recording_id,
            file_path="/data/calls/test_num.m4a",
            file_name="test_num.m4a",
            file_hash="hash_num",
            file_size=1000,
            status=RecordingStatus.DONE,
            duration_sec=60.0,
        )
        setup_session.add(recording)
        
        transcript = Transcript(
            recording_id=recording_id,
            model_name="test",
            language="he",
            text="hello world",
            segments_json=[
                {"start": 0.0, "end": 2.0, "text": "hello"},
            ]
        )
        setup_session.add(transcript)
        
        enrichment = Enrichment(
            recording_id=recording_id,
            diarization_enabled=False,
            diarization_pending=True,
            speaker_count=0
        )
        setup_session.add(enrichment)
        
        setup_session.commit()
        setup_session.close()

        def mock_get_session():
            return task_session_factory()

        with patch("app.worker.tasks.get_sync_session", mock_get_session):
            with patch("app.worker.tasks.get_settings") as mock_settings:
                mock_settings.return_value = get_test_settings()
                result = rediarize_recording(str(recording_id), num_speakers=3)

        assert result["status"] == "success"
        # Verify diarize_audio was called with num_speakers=3
        mock_processors["diarize"].assert_called_once()
        args, kwargs = mock_processors["diarize"].call_args
        assert kwargs["num_speakers"] == 3

    def test_enqueue_rediarization_tasks(self, task_session_factory):
        """Test enqueuing pending recordings."""
        setup_session = task_session_factory()
        
        # 1. Pending recording
        rid1 = uuid.uuid4()
        r1 = Recording(id=rid1, file_path="f1", file_name="n1", file_hash="h1", file_size=1, status=RecordingStatus.DONE)
        setup_session.add(r1)
        setup_session.add(Enrichment(recording_id=rid1, diarization_pending=True))
        
        # 2. Already done recording
        rid2 = uuid.uuid4()
        r2 = Recording(id=rid2, file_path="f2", file_name="n2", file_hash="h2", file_size=1, status=RecordingStatus.DONE)
        setup_session.add(r2)
        setup_session.add(Enrichment(recording_id=rid2, diarization_pending=False, diarization_enabled=True))
        
        setup_session.commit()
        setup_session.close()

        def mock_get_session():
            return task_session_factory()

        with patch("app.worker.tasks.get_sync_session", mock_get_session):
            with patch("app.worker.tasks.rediarize_recording.delay") as mock_delay:
                result = enqueue_rediarization_tasks(num_speakers=2)
                
        assert result["enqueued"] == 1
        mock_delay.assert_called_once_with(str(rid1), force=False, num_speakers=2)
