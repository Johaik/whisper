"""Unit tests for the folder watcher module."""

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.watcher.folder_watcher import FolderWatcher


class TestIsFileReady:
    """Tests for file readiness detection."""

    def test_rejects_recent_mtime(self, tmp_path: Path) -> None:
        """File modified less than stable_seconds ago is not ready."""
        test_file = tmp_path / "test.m4a"
        test_file.write_bytes(b"test content")

        watcher = FolderWatcher(
            folder=tmp_path,
            poll_interval=30,
            stable_seconds=10,
        )

        # File was just created, mtime is very recent
        assert watcher.is_file_ready(test_file) is False

    def test_rejects_first_size_check(self, tmp_path: Path) -> None:
        """First size observation returns False (need two polls)."""
        test_file = tmp_path / "test.m4a"
        test_file.write_bytes(b"test content")

        # Make file appear old
        old_mtime = time.time() - 60
        import os

        os.utime(test_file, (old_mtime, old_mtime))

        watcher = FolderWatcher(
            folder=tmp_path,
            poll_interval=30,
            stable_seconds=10,
        )

        # First observation - should return False
        assert watcher.is_file_ready(test_file) is False

    def test_rejects_changing_size(self, tmp_path: Path) -> None:
        """Size changed between polls returns False."""
        test_file = tmp_path / "test.m4a"
        test_file.write_bytes(b"initial content")

        old_mtime = time.time() - 60
        import os

        os.utime(test_file, (old_mtime, old_mtime))

        watcher = FolderWatcher(
            folder=tmp_path,
            poll_interval=30,
            stable_seconds=10,
        )

        # First observation
        watcher.is_file_ready(test_file)

        # Change the file size
        test_file.write_bytes(b"new longer content here")
        os.utime(test_file, (old_mtime, old_mtime))

        # Second observation with different size
        assert watcher.is_file_ready(test_file) is False

    def test_accepts_stable_file(self, tmp_path: Path) -> None:
        """Old mtime + stable size returns True."""
        test_file = tmp_path / "test.m4a"
        test_file.write_bytes(b"stable content")

        old_mtime = time.time() - 60
        import os

        os.utime(test_file, (old_mtime, old_mtime))

        watcher = FolderWatcher(
            folder=tmp_path,
            poll_interval=30,
            stable_seconds=10,
        )

        # First observation
        assert watcher.is_file_ready(test_file) is False

        # Second observation with same size
        assert watcher.is_file_ready(test_file) is True

    def test_handles_missing_file(self, tmp_path: Path) -> None:
        """Non-existent file returns False."""
        watcher = FolderWatcher(folder=tmp_path)
        missing_file = tmp_path / "nonexistent.m4a"

        assert watcher.is_file_ready(missing_file) is False


class TestScanFolder:
    """Tests for folder scanning."""

    def test_finds_audio_files(self, tmp_path: Path) -> None:
        """Finds files with audio extensions."""
        # Create test files
        (tmp_path / "audio1.m4a").write_bytes(b"test")
        (tmp_path / "audio2.mp3").write_bytes(b"test")
        (tmp_path / "audio3.wav").write_bytes(b"test")
        (tmp_path / "audio4.M4A").write_bytes(b"test")  # uppercase

        watcher = FolderWatcher(folder=tmp_path)
        files = watcher.scan_folder()

        assert len(files) == 4
        names = {f.name for f in files}
        assert "audio1.m4a" in names
        assert "audio2.mp3" in names
        assert "audio3.wav" in names
        assert "audio4.M4A" in names

    def test_ignores_non_audio(self, tmp_path: Path) -> None:
        """Ignores non-audio file extensions."""
        (tmp_path / "document.txt").write_bytes(b"test")
        (tmp_path / "document.pdf").write_bytes(b"test")
        (tmp_path / "audio.m4a").write_bytes(b"test")

        watcher = FolderWatcher(folder=tmp_path)
        files = watcher.scan_folder()

        assert len(files) == 1
        assert files[0].name == "audio.m4a"

    def test_empty_folder(self, tmp_path: Path) -> None:
        """Empty folder returns empty list."""
        watcher = FolderWatcher(folder=tmp_path)
        files = watcher.scan_folder()

        assert files == []


class TestCleanStaleCache:
    """Tests for stale cache cleanup."""

    def test_removes_deleted_files(self, tmp_path: Path) -> None:
        """Removes entries for deleted files."""
        watcher = FolderWatcher(folder=tmp_path)

        # Simulate cached file sizes
        watcher._last_sizes = {
            "/path/to/file1.m4a": 1000,
            "/path/to/file2.m4a": 2000,
            "/path/to/file3.m4a": 3000,
        }

        # Only file1 still exists
        current_files = {"/path/to/file1.m4a"}
        watcher.clean_stale_cache(current_files)

        assert "/path/to/file1.m4a" in watcher._last_sizes
        assert "/path/to/file2.m4a" not in watcher._last_sizes
        assert "/path/to/file3.m4a" not in watcher._last_sizes


class TestProcessFile:
    """Tests for file processing."""

    @patch("app.watcher.folder_watcher.SyncSessionLocal")
    @patch("app.watcher.folder_watcher.process_recording")
    @patch("app.watcher.folder_watcher.compute_file_hash")
    def test_creates_record_for_new_file(
        self,
        mock_hash: MagicMock,
        mock_task: MagicMock,
        mock_session_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """New file creates DB record."""
        test_file = tmp_path / "test.m4a"
        test_file.write_bytes(b"test content")

        mock_hash.return_value = "abc123hash"

        # Mock session
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session_class.return_value = mock_session

        watcher = FolderWatcher(folder=tmp_path)
        result = watcher.process_file(test_file)

        assert result is True
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @patch("app.watcher.folder_watcher.SyncSessionLocal")
    @patch("app.watcher.folder_watcher.process_recording")
    @patch("app.watcher.folder_watcher.compute_file_hash")
    def test_queues_task_for_new_file(
        self,
        mock_hash: MagicMock,
        mock_task: MagicMock,
        mock_session_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """New file dispatches Celery task."""
        test_file = tmp_path / "test.m4a"
        test_file.write_bytes(b"test content")

        mock_hash.return_value = "abc123hash"

        # Mock session with recording ID
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session_class.return_value = mock_session

        # Mock the recording object that gets created
        mock_recording = MagicMock()
        mock_recording.id = "test-uuid-123"

        # Set up session.refresh to populate the mock recording
        def refresh_side_effect(obj):
            obj.id = "test-uuid-123"

        mock_session.refresh.side_effect = refresh_side_effect

        watcher = FolderWatcher(folder=tmp_path)
        watcher.process_file(test_file)

        mock_task.delay.assert_called_once()

    @patch("app.watcher.folder_watcher.SyncSessionLocal")
    @patch("app.watcher.folder_watcher.process_recording")
    @patch("app.watcher.folder_watcher.compute_file_hash")
    def test_skips_existing_file(
        self,
        mock_hash: MagicMock,
        mock_task: MagicMock,
        mock_session_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """File already in DB is skipped."""
        test_file = tmp_path / "test.m4a"
        test_file.write_bytes(b"test content")

        mock_hash.return_value = "abc123hash"

        # Mock session with existing record
        mock_session = MagicMock()
        mock_existing = MagicMock()
        mock_existing.id = "existing-uuid"
        mock_session.query.return_value.filter.return_value.first.return_value = mock_existing
        mock_session_class.return_value = mock_session

        watcher = FolderWatcher(folder=tmp_path)
        result = watcher.process_file(test_file)

        assert result is False
        mock_session.add.assert_not_called()
        mock_task.delay.assert_not_called()


class TestPollOnce:
    """Tests for single poll operation."""

    def test_returns_stats(self, tmp_path: Path) -> None:
        """Poll returns stats dictionary."""
        watcher = FolderWatcher(folder=tmp_path)
        stats = watcher.poll_once()

        assert "scanned" in stats
        assert "ready" in stats
        assert "queued" in stats
        assert "skipped" in stats

    def test_handles_nonexistent_folder(self) -> None:
        """Handles non-existent folder gracefully."""
        watcher = FolderWatcher(folder="/nonexistent/path")
        stats = watcher.poll_once()

        assert stats["scanned"] == 0


class TestWatcherLifecycle:
    """Tests for watcher start/stop."""

    def test_stop_sets_running_false(self, tmp_path: Path) -> None:
        """Stop sets _running to False."""
        watcher = FolderWatcher(folder=tmp_path)
        watcher._running = True

        watcher.stop()

        assert watcher._running is False

