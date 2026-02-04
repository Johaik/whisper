"""Integration tests for the folder watcher service."""

import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.db.models import Recording, RecordingStatus
from app.watcher.folder_watcher import FolderWatcher


@pytest.fixture
def watch_folder(tmp_path: Path) -> Path:
    """Create a temporary folder for watching."""
    folder = tmp_path / "calls"
    folder.mkdir()
    return folder


@pytest.fixture
def watcher(watch_folder: Path) -> FolderWatcher:
    """Create a watcher instance for testing."""
    return FolderWatcher(
        folder=watch_folder,
        poll_interval=1,  # Fast for testing
        stable_seconds=1,  # Short for testing
    )


def create_stable_file(folder: Path, name: str, content: bytes = b"test audio data") -> Path:
    """Create a file that appears stable (old mtime)."""
    file_path = folder / name
    file_path.write_bytes(content)
    # Set mtime to 60 seconds ago
    old_mtime = time.time() - 60
    os.utime(file_path, (old_mtime, old_mtime))
    return file_path


class TestWatcherProcessesStableFile:
    """End-to-end test: file added, detected, queued."""

    @patch("app.watcher.folder_watcher.SyncSessionLocal")
    @patch("app.watcher.folder_watcher.compute_file_hash")
    def test_stable_file_gets_queued(
        self,
        mock_hash: MagicMock,
        mock_session_class: MagicMock,
        watch_folder: Path,
        watcher: FolderWatcher,
    ) -> None:
        """A stable file is detected and a record is queued (periodic enqueue_pending_recordings will enqueue)."""
        # Create a stable file
        test_file = create_stable_file(watch_folder, "test_audio.m4a")

        mock_hash.return_value = "stable_hash_123"

        # Mock session - file not in DB
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session_class.return_value = mock_session

        # First poll - records size but not ready yet
        stats1 = watcher.poll_once()
        assert stats1["scanned"] == 1
        assert stats1["queued"] == 0

        # Second poll - file is now ready, record created with QUEUED
        stats2 = watcher.poll_once()
        assert stats2["scanned"] == 1
        assert stats2["ready"] == 1
        assert stats2["queued"] == 1


class TestWatcherWaitsForStability:
    """File still changing is not queued."""

    def test_changing_file_not_queued(
        self,
        watch_folder: Path,
        watcher: FolderWatcher,
    ) -> None:
        """A file whose size keeps changing is not processed."""
        test_file = watch_folder / "changing.m4a"
        test_file.write_bytes(b"initial")
        old_mtime = time.time() - 60
        os.utime(test_file, (old_mtime, old_mtime))

        # First poll
        stats1 = watcher.poll_once()
        assert stats1["ready"] == 0

        # Change the file
        test_file.write_bytes(b"more content added")
        os.utime(test_file, (old_mtime, old_mtime))

        # Second poll - size changed, still not ready
        stats2 = watcher.poll_once()
        assert stats2["ready"] == 0

    def test_recently_modified_file_not_queued(
        self,
        watch_folder: Path,
    ) -> None:
        """A file with recent mtime is not processed."""
        watcher = FolderWatcher(
            folder=watch_folder,
            poll_interval=1,
            stable_seconds=30,  # Require 30s stability
        )

        test_file = watch_folder / "recent.m4a"
        test_file.write_bytes(b"test data")
        # File was just created, mtime is now

        # First poll
        stats1 = watcher.poll_once()
        assert stats1["scanned"] == 1
        assert stats1["ready"] == 0

        # Second poll - file is still too recent
        stats2 = watcher.poll_once()
        assert stats2["ready"] == 0


class TestWatcherHandlesConcurrentFiles:
    """Multiple files queued correctly."""

    @patch("app.watcher.folder_watcher.SyncSessionLocal")
    @patch("app.watcher.folder_watcher.compute_file_hash")
    def test_multiple_files_processed(
        self,
        mock_hash: MagicMock,
        mock_session_class: MagicMock,
        watch_folder: Path,
        watcher: FolderWatcher,
    ) -> None:
        """Multiple stable files are all queued (periodic enqueue_pending_recordings will enqueue)."""
        # Create multiple stable files
        create_stable_file(watch_folder, "audio1.m4a")
        create_stable_file(watch_folder, "audio2.mp3")
        create_stable_file(watch_folder, "audio3.wav")

        # Return different hashes for each file
        hash_counter = [0]

        def hash_side_effect(path: str) -> str:
            hash_counter[0] += 1
            return f"hash_{hash_counter[0]}"

        mock_hash.side_effect = hash_side_effect

        # Mock session - files not in DB
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session_class.return_value = mock_session

        # First poll - records sizes
        stats1 = watcher.poll_once()
        assert stats1["scanned"] == 3
        assert stats1["queued"] == 0

        # Second poll - all files ready, three records created with QUEUED
        stats2 = watcher.poll_once()
        assert stats2["scanned"] == 3
        assert stats2["ready"] == 3
        assert stats2["queued"] == 3


class TestWatcherWithDatabase:
    """Integration tests with actual database."""

    @pytest.fixture
    def watcher_with_db(
        self, watch_folder: Path, db_session: Session
    ) -> tuple[FolderWatcher, Session]:
        """Create watcher with real database session."""
        watcher = FolderWatcher(
            folder=watch_folder,
            poll_interval=1,
            stable_seconds=1,
        )
        return watcher, db_session

    def test_creates_recording_in_database(
        self,
        watch_folder: Path,
        db_session: Session,
    ) -> None:
        """New file creates recording in database."""
        # Create stable file
        test_file = create_stable_file(watch_folder, "db_test.m4a", b"test audio content")

        watcher = FolderWatcher(
            folder=watch_folder,
            poll_interval=1,
            stable_seconds=1,
        )

        # Patch to use our test session
        with patch("app.watcher.folder_watcher.SyncSessionLocal") as mock_session_class:
            mock_session_class.return_value = db_session

            # First poll - records size
            watcher.poll_once()

            # Second poll - should create record
            stats = watcher.poll_once()

            assert stats["queued"] == 1

        # Verify recording exists in DB
        recording = db_session.query(Recording).filter(
            Recording.file_name == "db_test.m4a"
        ).first()

        assert recording is not None
        assert recording.status == RecordingStatus.QUEUED
        assert recording.file_size > 0
        assert recording.file_hash is not None

    def test_skips_already_processed_file(
        self,
        watch_folder: Path,
        db_session: Session,
    ) -> None:
        """File already in DB is not queued again."""
        # Create and add file to DB first
        test_file = create_stable_file(watch_folder, "existing.m4a", b"existing content")

        from app.processors.metadata import compute_file_hash

        file_hash = compute_file_hash(str(test_file))

        existing_recording = Recording(
            file_path=str(test_file),
            file_name="existing.m4a",
            file_hash=file_hash,
            file_size=test_file.stat().st_size,
            status=RecordingStatus.DONE,
        )
        db_session.add(existing_recording)
        db_session.commit()

        watcher = FolderWatcher(
            folder=watch_folder,
            poll_interval=1,
            stable_seconds=1,
        )

        with patch("app.watcher.folder_watcher.SyncSessionLocal") as mock_session_class:
            mock_session_class.return_value = db_session

            # Two polls
            watcher.poll_once()
            stats = watcher.poll_once()

            # File should be skipped
            assert stats["ready"] == 1
            assert stats["skipped"] == 1
            assert stats["queued"] == 0

