"""Unit tests for the metadata processor."""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.processors.metadata import AudioMetadata, compute_file_hash, extract_metadata


class TestComputeFileHash:
    """Tests for file hashing."""

    def test_hash_is_consistent(self, temp_audio_file):
        """Test that hash is consistent for same file."""
        hash1 = compute_file_hash(str(temp_audio_file))
        hash2 = compute_file_hash(str(temp_audio_file))
        assert hash1 == hash2

    def test_hash_is_sha256_format(self, temp_audio_file):
        """Test that hash is proper SHA256 hex string."""
        file_hash = compute_file_hash(str(temp_audio_file))
        assert len(file_hash) == 64
        assert all(c in "0123456789abcdef" for c in file_hash)

    def test_different_files_have_different_hashes(self):
        """Test that different files produce different hashes."""
        with tempfile.NamedTemporaryFile(delete=False) as f1:
            f1.write(b"content1")
            path1 = f1.name

        with tempfile.NamedTemporaryFile(delete=False) as f2:
            f2.write(b"content2")
            path2 = f2.name

        try:
            hash1 = compute_file_hash(path1)
            hash2 = compute_file_hash(path2)
            assert hash1 != hash2
        finally:
            Path(path1).unlink()
            Path(path2).unlink()


class TestExtractMetadata:
    """Tests for metadata extraction."""

    def test_file_not_found_raises_error(self):
        """Test that missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            extract_metadata("/nonexistent/file.wav")

    @patch("app.processors.metadata.subprocess.run")
    def test_extracts_duration(self, mock_run, temp_audio_file, mock_ffprobe_output):
        """Test that duration is extracted correctly."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps(mock_ffprobe_output),
            returncode=0,
        )

        result = extract_metadata(str(temp_audio_file))

        assert result.duration_sec == pytest.approx(60.123456)

        # Verify absolute path is used
        cmd = mock_run.call_args[0][0]
        input_path = cmd[-1]
        assert os.path.isabs(input_path), f"Input path '{input_path}' should be absolute"

    @patch("app.processors.metadata.subprocess.run")
    def test_extracts_audio_stream_info(self, mock_run, temp_audio_file, mock_ffprobe_output):
        """Test that audio stream info is extracted."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps(mock_ffprobe_output),
            returncode=0,
        )

        result = extract_metadata(str(temp_audio_file))

        assert result.sample_rate == 44100
        assert result.channels == 2
        assert result.codec == "aac"

    @patch("app.processors.metadata.subprocess.run")
    def test_extracts_file_info(self, mock_run, temp_audio_file, mock_ffprobe_output):
        """Test that file info is included."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps(mock_ffprobe_output),
            returncode=0,
        )

        result = extract_metadata(str(temp_audio_file))

        assert result.file_size > 0
        assert len(result.file_hash) == 64

    @patch("app.processors.metadata.subprocess.run")
    def test_stores_raw_metadata(self, mock_run, temp_audio_file, mock_ffprobe_output):
        """Test that raw ffprobe output is stored."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps(mock_ffprobe_output),
            returncode=0,
        )

        result = extract_metadata(str(temp_audio_file))

        assert result.raw_metadata == mock_ffprobe_output

    @patch("app.processors.metadata.subprocess.run")
    def test_handles_missing_audio_stream(self, mock_run, temp_audio_file):
        """Test handling of file with no audio stream."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"format": {"duration": "10"}, "streams": []}),
            returncode=0,
        )

        result = extract_metadata(str(temp_audio_file))

        assert result.sample_rate is None
        assert result.channels is None
        assert result.codec is None

    @patch("app.processors.metadata.subprocess.run")
    def test_ffprobe_failure_raises_error(self, mock_run, temp_audio_file):
        """Test that ffprobe failure raises RuntimeError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "ffprobe", stderr="Error"
        )

        with pytest.raises(RuntimeError, match="ffprobe failed"):
            extract_metadata(str(temp_audio_file))

    @patch("app.processors.metadata.subprocess.run")
    def test_ffprobe_timeout_raises_error(self, mock_run, temp_audio_file):
        """Test that ffprobe timeout raises RuntimeError."""
        mock_run.side_effect = subprocess.TimeoutExpired("ffprobe", 30)

        with pytest.raises(RuntimeError, match="timed out"):
            extract_metadata(str(temp_audio_file))

    @patch("app.processors.metadata.logger")
    @patch("app.processors.metadata.subprocess.run")
    def test_invalid_json_raises_error(self, mock_run, mock_logger, temp_audio_file):
        """Test that invalid JSON from ffprobe raises error."""
        mock_run.return_value = MagicMock(
            stdout="not valid json",
            returncode=0,
        )

        with pytest.raises(RuntimeError, match="Failed to parse") as exc_info:
            extract_metadata(str(temp_audio_file))

        # Verify error was logged
        mock_logger.error.assert_called_once()
        assert "Failed to parse ffprobe output" in mock_logger.error.call_args[0][0]

        # Verify exception chaining
        assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)
