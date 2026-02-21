"""Unit tests for audio loading in diarization processor."""

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock all dependencies before they are imported by app.processors.diarize
# This ensures the tests can run even in environments with missing dependencies.
mock_modules = {
    "pydantic": MagicMock(),
    "pydantic_settings": MagicMock(),
    "torchaudio": MagicMock(),
    "torchaudio.transforms": MagicMock(),
    "torch": MagicMock(),
    "pyannote.audio": MagicMock(),
}

# Add special handling for BaseSettings inheritance and field_validator decorator
class MockBaseSettings:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

mock_modules["pydantic_settings"].BaseSettings = MockBaseSettings
mock_modules["pydantic"].field_validator = lambda *args, **kwargs: lambda f: f

# Setup waveform mock for log formatting
mock_waveform = MagicMock()
mock_waveform.shape = [1, 16000]
mock_modules["torch"].zeros.return_value = mock_waveform

# Permanently put mocks into sys.modules for the duration of this test module
for mod_name, mock_obj in mock_modules.items():
    sys.modules[mod_name] = mock_obj

from app.processors.diarize import _load_audio_as_waveform


class TestLoadAudioAsWaveform:
    """Tests for _load_audio_as_waveform function."""

    @patch("app.processors.diarize.subprocess.run")
    def test_load_audio_ffmpeg_failure(self, mock_run):
        """Test that ffmpeg failure raises a descriptive RuntimeError."""
        # Setup: Direct load fails
        with patch("app.processors.diarize.torchaudio") as mock_torchaudio, \
             patch("app.processors.diarize.HAS_DIARIZE_DEPS", True):
            mock_load = mock_torchaudio.load
            mock_load.side_effect = [Exception("Direct load failed"), MagicMock()]

            # Setup: ffmpeg fails
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=1,
                cmd="ffmpeg ...",
                stderr="ffmpeg: error while loading shared libraries"
            )

            # Execute & Verify
            with pytest.raises(RuntimeError) as excinfo:
                _load_audio_as_waveform("invalid_audio.m4a")

            assert "Failed to convert audio to WAV via ffmpeg" in str(excinfo.value)
            assert "ffmpeg: error while loading shared libraries" in str(excinfo.value)

    @patch("app.processors.diarize.subprocess.run")
    @patch("os.path.exists")
    @patch("os.unlink")
    def test_load_audio_ffmpeg_success(self, mock_unlink, mock_exists, mock_run):
        """Test that ffmpeg success works correctly."""
        # Setup: Direct load fails
        with patch("app.processors.diarize.torchaudio") as mock_torchaudio, \
             patch("app.processors.diarize.HAS_DIARIZE_DEPS", True):
            mock_load = mock_torchaudio.load
            test_waveform = MagicMock()
            test_waveform.shape = [1, 16000]
            mock_load.side_effect = [Exception("Direct load failed"), (test_waveform, 16000)]

            # Setup: ffmpeg succeeds
            mock_run.return_value = MagicMock(returncode=0)
            mock_exists.return_value = True

            # Execute
            waveform, sample_rate = _load_audio_as_waveform("audio.m4a")

            # Verify
            assert waveform == test_waveform
            assert sample_rate == 16000
            mock_run.assert_called_once()
            mock_unlink.assert_called_once()
