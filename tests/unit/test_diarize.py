"""Unit tests for the diarization processor."""

from unittest.mock import MagicMock, patch

from app.processors.diarize import (
    diarize_audio,
    assign_speakers_to_transcript,
    DiarizationResult,
    DiarizationSegment,
)
from app.processors.transcribe import TranscriptSegment

class TestAssignSpeakersToTranscript:
    """Tests for assign_speakers_to_transcript function."""

    def test_assigns_speakers_based_on_overlap(self):
        """Test that speakers are assigned based on maximum overlap."""
        # 0-2: Seg1
        # 0-1: Spk1, 1-3: Spk2
        # Seg1 (0-2) overlaps Spk1 (0-1) by 1.0, Spk2 (1-2) by 1.0.
        # Wait, if equal overlap? The code: if overlap > best_overlap.
        # So first one wins if strict inequality. Or last one?
        # best_overlap init 0.0.
        # Spk1: overlap=1.0. 1.0 > 0.0 -> best=Spk1.
        # Spk2: overlap=1.0. 1.0 > 1.0 is False.
        # So Spk1 wins.

        t_segs = [
            TranscriptSegment(start=0.0, end=2.0, text="Hello"),
            TranscriptSegment(start=2.5, end=4.0, text="World"),
        ]

        d_segs = [
            DiarizationSegment(start=0.0, end=1.0, speaker="SPEAKER_1"),
            DiarizationSegment(start=1.0, end=3.0, speaker="SPEAKER_2"),
            DiarizationSegment(start=3.0, end=5.0, speaker="SPEAKER_1"),
        ]

        diarization = DiarizationResult(
            segments=d_segs,
            speaker_count=2,
            speakers=["SPEAKER_1", "SPEAKER_2"]
        )

        result = assign_speakers_to_transcript(t_segs, diarization)

        # Seg1 (0-2): overlaps Spk1 (0-1) [1s], Spk2 (1-3) -> (1-2) [1s].
        # As analyzed, Spk1 should win due to strict inequality check > best.
        assert result[0].speaker == "SPEAKER_1"

        # Seg2 (2.5-4.0):
        # Spk2 (1-3) -> (2.5-3.0) [0.5s]
        # Spk1 (3-5) -> (3.0-4.0) [1.0s]
        # Spk1 has more overlap.
        assert result[1].speaker == "SPEAKER_1"

    def test_handles_no_overlap(self):
        """Test handling of segments with no speaker overlap."""
        t_segs = [TranscriptSegment(start=0.0, end=1.0, text="Hello")]
        d_segs = [DiarizationSegment(start=2.0, end=3.0, speaker="SPEAKER_1")]

        diarization = DiarizationResult(segments=d_segs, speaker_count=1, speakers=["SPEAKER_1"])

        result = assign_speakers_to_transcript(t_segs, diarization)

        assert result[0].speaker is None

    def test_handles_empty_diarization(self):
        """Test handling of empty diarization result."""
        t_segs = [TranscriptSegment(start=0.0, end=1.0, text="Hello")]
        diarization = DiarizationResult(segments=[], speaker_count=0, speakers=[])

        result = assign_speakers_to_transcript(t_segs, diarization)

        assert len(result) == 1
        assert result[0].speaker is None


class TestDiarizeAudio:
    """Tests for diarize_audio function."""

    @patch("app.processors.diarize.get_or_load_pipeline")
    @patch("app.processors.diarize._load_audio_as_waveform")
    def test_diarize_calls_pipeline_with_num_speakers(self, mock_load_audio, mock_get_pipeline, test_settings):
        """Test that num_speakers is passed to the pipeline."""
        mock_pipeline = MagicMock()
        mock_get_pipeline.return_value = mock_pipeline

        # Mock waveform load
        mock_waveform = MagicMock()
        mock_waveform.shape = (1, 16000)
        mock_load_audio.return_value = (mock_waveform, 16000)

        # Mock output
        mock_annotation = MagicMock()
        mock_annotation.itertracks.return_value = iter([]) # Empty iterator

        # Handle the hasattr check in diarize_audio
        # If pipeline returns an object with speaker_diarization attr, it uses that.
        # Otherwise it uses the object directly.
        # We'll make it return the annotation directly to simplify.
        mock_pipeline.return_value = mock_annotation

        with patch("app.processors.diarize.get_settings", return_value=test_settings):
            # Enable diarization in settings
            test_settings.diarization_enabled = True

            diarize_audio("/path/to/audio.wav", num_speakers=2)

        # Verify pipeline call
        mock_pipeline.assert_called_once()
        call_args, call_kwargs = mock_pipeline.call_args

        # Check that waveform dict was passed
        assert "waveform" in call_args[0]
        assert "sample_rate" in call_args[0]

        # Check that num_speakers was passed in kwargs
        assert call_kwargs["num_speakers"] == 2

    @patch("app.processors.diarize.get_or_load_pipeline")
    @patch("app.processors.diarize._load_audio_as_waveform")
    def test_diarize_without_num_speakers(self, mock_load_audio, mock_get_pipeline, test_settings):
        """Test that num_speakers is not passed if None."""
        mock_pipeline = MagicMock()
        mock_get_pipeline.return_value = mock_pipeline

        mock_waveform = MagicMock()
        mock_waveform.shape = (1, 16000)
        mock_load_audio.return_value = (mock_waveform, 16000)

        mock_annotation = MagicMock()
        mock_annotation.itertracks.return_value = iter([])
        mock_pipeline.return_value = mock_annotation

        with patch("app.processors.diarize.get_settings", return_value=test_settings):
            test_settings.diarization_enabled = True
            diarize_audio("/path/to/audio.wav")

        mock_pipeline.assert_called_once()
        _, call_kwargs = mock_pipeline.call_args

        assert "num_speakers" not in call_kwargs
