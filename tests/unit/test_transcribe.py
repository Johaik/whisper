"""Unit tests for the transcription processor."""

import pytest
from unittest.mock import MagicMock, patch

from app.processors.transcribe import (
    TranscriptSegment,
    TranscriptionResult,
    get_or_load_model,
    segments_to_json,
    transcribe_audio,
)


class TestTranscriptSegment:
    """Tests for TranscriptSegment dataclass."""

    def test_create_segment_without_speaker(self):
        """Test creating a segment without speaker info."""
        segment = TranscriptSegment(start=0.0, end=2.5, text="Hello world")
        assert segment.start == 0.0
        assert segment.end == 2.5
        assert segment.text == "Hello world"
        assert segment.speaker is None

    def test_create_segment_with_speaker(self):
        """Test creating a segment with speaker info."""
        segment = TranscriptSegment(
            start=1.0, end=3.0, text="Test text", speaker="SPEAKER_0"
        )
        assert segment.speaker == "SPEAKER_0"


class TestSegmentsToJson:
    """Tests for segments_to_json function."""

    def test_empty_segments(self):
        """Test with empty segment list."""
        result = segments_to_json([])
        assert result == []

    def test_single_segment(self):
        """Test with a single segment."""
        segments = [TranscriptSegment(start=0.0, end=1.0, text="Test")]
        result = segments_to_json(segments)
        assert len(result) == 1
        assert result[0] == {
            "start": 0.0,
            "end": 1.0,
            "text": "Test",
            "speaker": None,
        }

    def test_multiple_segments_with_speakers(self, sample_segments):
        """Test with multiple segments including speakers."""
        result = segments_to_json(sample_segments)
        assert len(result) == 3
        assert result[0]["speaker"] == "SPEAKER_0"
        assert result[1]["speaker"] == "SPEAKER_1"
        assert result[2]["speaker"] == "SPEAKER_0"


class TestGetOrLoadModel:
    """Tests for model loading and caching."""

    def test_loads_model_with_correct_params(self):
        """Test that model is loaded with correct parameters."""
        # Clear cache first
        from app.processors.transcribe import _model_cache
        _model_cache.clear()

        with patch("faster_whisper.WhisperModel") as mock_model_class:
            mock_model_class.return_value = MagicMock()

            model = get_or_load_model(
                model_name="test-model",
                device="cpu",
                compute_type="int8",
            )

            mock_model_class.assert_called_once_with(
                "test-model",
                device="cpu",
                compute_type="int8",
            )

    def test_caches_model(self):
        """Test that model is cached and reused."""
        from app.processors.transcribe import _model_cache
        _model_cache.clear()

        with patch("faster_whisper.WhisperModel") as mock_model_class:
            mock_model_class.return_value = MagicMock()

            # Load twice
            model1 = get_or_load_model("test-model", "cpu", "int8")
            model2 = get_or_load_model("test-model", "cpu", "int8")

            # Should only create once
            assert mock_model_class.call_count == 1
            assert model1 is model2


class TestTranscribeAudio:
    """Tests for transcribe_audio function."""

    @patch("app.processors.transcribe.get_or_load_model")
    def test_transcribe_returns_result(self, mock_get_model, mock_whisper_model):
        """Test that transcription returns proper result."""
        mock_get_model.return_value = mock_whisper_model

        result = transcribe_audio("/path/to/audio.wav")

        assert isinstance(result, TranscriptionResult)
        assert result.language == "he"
        assert result.language_probability == 0.95
        assert len(result.segments) == 2
        assert "שלום עולם" in result.text

    @patch("app.processors.transcribe.get_or_load_model")
    def test_transcribe_uses_settings_defaults(self, mock_get_model, mock_whisper_model, test_settings):
        """Test that transcription uses settings defaults."""
        mock_get_model.return_value = mock_whisper_model

        with patch("app.processors.transcribe.get_settings", return_value=test_settings):
            result = transcribe_audio("/path/to/audio.wav")

        # Verify model was called with correct language
        mock_whisper_model.transcribe.assert_called_once()
        call_kwargs = mock_whisper_model.transcribe.call_args[1]
        assert call_kwargs["language"] == "he"

    @patch("app.processors.transcribe.get_or_load_model")
    def test_transcribe_custom_beam_size(self, mock_get_model, mock_whisper_model):
        """Test transcription with custom beam size."""
        mock_get_model.return_value = mock_whisper_model

        result = transcribe_audio("/path/to/audio.wav", beam_size=10)

        assert result.beam_size == 10

    @patch("app.processors.transcribe.get_or_load_model")
    def test_transcribe_handles_empty_segments(self, mock_get_model):
        """Test transcription with no segments."""
        mock_model = MagicMock()
        mock_info = MagicMock()
        mock_info.language = "he"
        mock_info.language_probability = 0.5
        mock_model.transcribe.return_value = (iter([]), mock_info)
        mock_get_model.return_value = mock_model

        result = transcribe_audio("/path/to/audio.wav")

        assert result.text == ""
        assert len(result.segments) == 0

