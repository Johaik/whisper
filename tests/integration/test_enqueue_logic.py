
import uuid
from unittest.mock import patch, MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests.conftest import _test_db_reachable, get_test_settings, USE_SQLITE
from app.db.models import Base, Recording, RecordingStatus
from app.worker.tasks import enqueue_pending_recordings

pytestmark = pytest.mark.integration

class TestEnqueueLogic:
    @pytest.fixture
    def db_engine(self):
        if not _test_db_reachable():
            pytest.skip("Test Postgres not reachable")
        settings = get_test_settings()
        connect_args = {"check_same_thread": False} if USE_SQLITE else {}
        engine = create_engine(settings.database_url_sync, connect_args=connect_args)
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        yield engine
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

    @pytest.fixture
    def session_factory(self, db_engine):
        return sessionmaker(bind=db_engine)

    def test_enqueue_recordings_batches_updates(self, session_factory):
        """Test that QUEUED recordings are updated to PROCESSING and tasks are dispatched."""
        # Create 3 queued recordings
        session = session_factory()
        recordings = []
        for i in range(3):
            rec = Recording(
                id=uuid.uuid4(),
                file_path=f"/tmp/test_{i}.m4a",
                file_name=f"test_{i}.m4a",
                file_hash=f"hash_{i}",
                file_size=1000,
                status=RecordingStatus.QUEUED,
            )
            recordings.append(rec)
            session.add(rec)
        session.commit()
        ids = [str(r.id) for r in recordings]
        session.close()

        # Mock dependencies
        with patch("app.worker.tasks.get_sync_session", lambda: session_factory()), \
             patch("app.worker.tasks.process_recording.delay") as mock_delay, \
             patch("app.worker.tasks.get_settings") as mock_settings:

            mock_settings.return_value = get_test_settings()

            # Run the task
            result = enqueue_pending_recordings()

            # Verify results
            assert result["enqueued"] == 3
            assert mock_delay.call_count == 3

            # Verify mock calls args
            called_ids = [call.args[0] for call in mock_delay.call_args_list]
            assert set(called_ids) == set(ids)

            # Verify DB state
            verify_session = session_factory()
            for r_id in ids:
                rec = verify_session.query(Recording).filter(Recording.id == uuid.UUID(r_id)).first()
                assert rec.status == RecordingStatus.PROCESSING
            verify_session.close()

    def test_enqueue_handles_empty_queue(self, session_factory):
        """Test that nothing happens when queue is empty."""
        with patch("app.worker.tasks.get_sync_session", lambda: session_factory()), \
             patch("app.worker.tasks.process_recording.delay") as mock_delay, \
             patch("app.worker.tasks.get_settings") as mock_settings:

            mock_settings.return_value = get_test_settings()
            result = enqueue_pending_recordings()

            assert result["enqueued"] == 0
            mock_delay.assert_not_called()
