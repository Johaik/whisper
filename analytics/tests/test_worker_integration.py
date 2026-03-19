import pytest
import uuid
from unittest.mock import MagicMock, patch
from app.worker.tasks import process_recording

def test_analytics_trigger_in_worker():
    """Verify that analytics tasks are triggered after processing a recording."""
    recording_id = "123e4567-e89b-12d3-a456-426614174000"
    
    with patch("app.worker.tasks.get_sync_session") as mock_session_getter:
        mock_session = MagicMock()
        mock_session_getter.return_value = mock_session
        
        # Mock Recording lookup
        mock_recording = MagicMock()
        mock_recording.status = "queued"
        mock_recording.id = uuid.UUID(recording_id)
        mock_recording.retry_count = 0
        mock_session.query.return_value.filter.return_value.first.return_value = mock_recording
        
        # Mock all the heavy lifting functions imported in tasks.py
        with patch("app.worker.tasks.parse_recording_filename"), \
             patch("app.worker.tasks.extract_metadata") as mock_extract, \
             patch("app.worker.tasks.transcribe_audio") as mock_transcribe, \
             patch("app.worker.tasks.diarize_audio"), \
             patch("app.worker.tasks.compute_analytics"), \
             patch("app.worker.tasks._store_processing_results"):
            
            mock_extract.return_value = MagicMock(duration_sec=60)
            mock_transcribe.return_value = MagicMock(segments=[])

            # This is the call we want to verify (our new hook)
            with patch("app.worker.tasks.trigger_advanced_analytics") as mock_trigger:
                # Based on inspection, .run only takes recording_id due to autoretry decorator
                process_recording.run(recording_id)
                mock_trigger.assert_called_once_with(uuid.UUID(recording_id), mock_session)
