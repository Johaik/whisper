"""Unit tests for the folder watcher module."""

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.db.models import RecordingStatus
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


class TestProcessBatch:
    """Tests for batch file processing."""

    @patch("app.watcher.folder_watcher.SyncSessionLocal")
    @patch("app.watcher.folder_watcher.compute_file_hash")
    def test_creates_record_for_new_file(
        self,
        mock_hash: MagicMock,
        mock_session_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """New file creates DB record with QUEUED status."""
        test_file = tmp_path / "test.m4a"
        test_file.write_bytes(b"test content")

        mock_hash.return_value = "abc123hash"

        # Mock session
        mock_session = MagicMock()
        # Mock query results for bulk check (return empty lists => no existing files)
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mock_session_class.return_value = mock_session

        watcher = FolderWatcher(folder=tmp_path)
        result = watcher.process_batch([test_file])

        assert result == 1
        mock_session.add_all.assert_called_once()
        mock_session.commit.assert_called_once()

    @patch("app.watcher.folder_watcher.SyncSessionLocal")
    @patch("app.watcher.folder_watcher.compute_file_hash")
    def test_new_file_record_has_queued_status(
        self,
        mock_hash: MagicMock,
        mock_session_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """New file creates recording with status QUEUED."""
        test_file = tmp_path / "test.m4a"
        test_file.write_bytes(b"test content")

        mock_hash.return_value = "abc123hash"

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mock_session_class.return_value = mock_session

        watcher = FolderWatcher(folder=tmp_path)
        watcher.process_batch([test_file])

        call_args = mock_session.add_all.call_args
        assert call_args is not None
        # add_all takes a list
        recordings = call_args[0][0]
        assert len(recordings) == 1
        assert recordings[0].status == RecordingStatus.QUEUED

    @patch("app.watcher.folder_watcher.SyncSessionLocal")
    @patch("app.watcher.folder_watcher.compute_file_hash")
    def test_skips_existing_file(
        self,
        mock_hash: MagicMock,
        mock_session_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """File already in DB is skipped."""
        test_file = tmp_path / "test.m4a"
        test_file.write_bytes(b"test content")

        mock_hash.return_value = "abc123hash"

        # Mock session with existing record
        mock_session = MagicMock()

        # We make the mock return a list with an object having file_hash
        mock_existing_hash = MagicMock()
        mock_existing_hash.file_hash = "abc123hash"

        # For the first query (hashes) return match, for second (names) return empty
        # or just make it return the match for the hash query

        # We need to distinguish between the two queries (hash and name)
        # However, mock chaining is tricky.
        # Simpler: just return a list containing the hash for any query.

        mock_session.query.return_value.filter.return_value.all.return_value = [mock_existing_hash]

        mock_session_class.return_value = mock_session

        watcher = FolderWatcher(folder=tmp_path)
        result = watcher.process_batch([test_file])

        assert result == 0
        mock_session.add_all.assert_not_called()

    @patch("app.watcher.folder_watcher.SyncSessionLocal")
    @patch("app.watcher.folder_watcher.compute_file_hash")
    def test_skips_intra_batch_duplicates(
        self,
        mock_hash: MagicMock,
        mock_session_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Duplicates within the same batch are skipped."""
        file1 = tmp_path / "file1.m4a"
        file1.write_bytes(b"content")
        file2 = tmp_path / "file2.m4a"
        file2.write_bytes(b"content")  # Same content -> same hash

        mock_hash.return_value = "samehash"

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mock_session_class.return_value = mock_session

        watcher = FolderWatcher(folder=tmp_path)
        # Process both files in one batch
        result = watcher.process_batch([file1, file2])

        assert result == 1

        call_args = mock_session.add_all.call_args
        assert call_args is not None
        recordings = call_args[0][0]
        assert len(recordings) == 1


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


class TestGetPendingCount:
    """Tests for pending file counting optimization."""

    @patch("app.watcher.folder_watcher.SyncSessionLocal")
    @patch("app.watcher.folder_watcher.compute_file_hash")
    def test_optimized_pending_count(
        self,
        mock_hash: MagicMock,
        mock_session_cls: MagicMock,
        tmp_path: Path
    ) -> None:
        """Test that pending count uses batching and correct precedence."""
        # Setup
        watcher = FolderWatcher(folder=tmp_path)

        # Create 3 files
        files = ["f1.mp3", "f2.mp3", "f3.mp3"]
        for f in files:
            (tmp_path / f).touch()

        # Mock session
        session = MagicMock()
        mock_session_cls.return_value = session

        # f1: exists by name
        # f2: exists by hash
        # f3: new

        mock_hash.side_effect = lambda x: f"hash_{Path(x).name}"

        # First query result: existing names (f1)
        # Second query result: existing hashes (f2)
        # We need to structure the mock to return these results sequentially for .all() calls
        session.query.return_value.filter.return_value.all.side_effect = [
            [("f1.mp3",)],       # Names found
            [("hash_f2.mp3",)]   # Hashes found
        ]

        count = watcher.get_pending_count_in_folder()

        assert count == 1 # Only f3 is pending

        # Verify that compute_file_hash was NOT called for f1 (since it was found by name)
        called_paths = [Path(c[0][0]).name for c in mock_hash.call_args_list]
        assert "f1.mp3" not in called_paths
        assert "f2.mp3" in called_paths
        assert "f3.mp3" in called_paths

    @patch("app.watcher.folder_watcher.SyncSessionLocal")
    @patch("app.watcher.folder_watcher.compute_file_hash")
    def test_batching_logic(
        self,
        mock_hash: MagicMock,
        mock_session_cls: MagicMock,
        tmp_path: Path
    ) -> None:
        """Test that large file lists are batched correctly."""
        # Setup with enough files to trigger batching (batch size is 500)
        watcher = FolderWatcher(folder=tmp_path)

        # Create 550 files
        for i in range(550):
            (tmp_path / f"file_{i}.mp3").touch()

        session = MagicMock()
        mock_session_cls.return_value = session

        # Assume no files exist
        session.query.return_value.filter.return_value.all.return_value = []
        mock_hash.return_value = "dummy_hash"

        watcher.get_pending_count_in_folder()

        # 550 files / 500 batch size = 2 batches for names
        # 2 batches for hashes (since no names found)
        # Total 4 calls to all()
        assert session.query.return_value.filter.return_value.all.call_count == 4
