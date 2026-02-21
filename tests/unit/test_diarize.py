"""Unit tests for the diarization processor."""

from unittest.mock import MagicMock, patch

import pytest

from app.processors.diarize import (
    DiarizationResult,
    DiarizationSegment,
    assign_speakers_to_transcript,
    diarize_audio,
    get_or_load_pipeline,
)
from app.processors.transcribe import TranscriptSegment


class TestDiarizationSegment:
    """Tests for DiarizationSegment dataclass."""

    def test_create_segment(self):
        """Test creating a diarization segment."""
        segment = DiarizationSegment(start=0.0, end=5.0, speaker="SPEAKER_0")
        assert segment.start == 0.0
        assert segment.end == 5.0
        assert segment.speaker == "SPEAKER_0"


class TestDiarizationResult:
    """Tests for DiarizationResult dataclass."""

    def test_create_result(self):
        """Test creating a diarization result."""
        segments = [
            DiarizationSegment(start=0.0, end=5.0, speaker="SPEAKER_0"),
            DiarizationSegment(start=5.0, end=10.0, speaker="SPEAKER_1"),
        ]
        result = DiarizationResult(
            segments=segments,
            speaker_count=2,
            speakers=["SPEAKER_0", "SPEAKER_1"],
        )
        assert len(result.segments) == 2
        assert result.speaker_count == 2


class TestDiarizeAudio:
    """Tests for diarize_audio function."""

    @patch("app.processors.diarize.get_settings")
    def test_returns_empty_when_disabled(self, mock_settings):
        """Test that empty result is returned when diarization is disabled."""
        mock_settings.return_value.diarization_enabled = False

        result = diarize_audio("/path/to/audio.wav")

        assert result.segments == []
        assert result.speaker_count == 0

    @patch("app.processors.diarize._load_audio_as_waveform")
    @patch("app.processors.diarize.get_or_load_pipeline")
    @patch("app.processors.diarize.get_settings")
    def test_processes_audio_when_enabled(self, mock_settings, mock_get_pipeline, mock_load_audio):
        """Test that audio is processed when diarization is enabled."""
        mock_settings.return_value.diarization_enabled = True

        # Mock audio loading - use MagicMock for the waveform tensor to avoid torch dependency in tests
        mock_waveform = MagicMock()
        mock_waveform.shape = [1, 16000]
        mock_load_audio.return_value = (mock_waveform, 16000)

        # Mock pyannote pipeline
        mock_pipeline = MagicMock()
        mock_diarization_output = MagicMock()
        mock_annotation = MagicMock()

        # Create mock turns
        mock_turn1 = MagicMock()
        mock_turn1.start = 0.0
        mock_turn1.end = 5.0

        mock_turn2 = MagicMock()
        mock_turn2.start = 5.0
        mock_turn2.end = 10.0

        mock_annotation.itertracks.return_value = [
            (mock_turn1, None, "SPEAKER_0"),
            (mock_turn2, None, "SPEAKER_1"),
        ]
        
        # Handle pyannote 4.0 output format
        mock_diarization_output.speaker_diarization = mock_annotation

        mock_pipeline.return_value = mock_diarization_output
        mock_get_pipeline.return_value = mock_pipeline

        result = diarize_audio("/path/to/audio.wav")

        assert len(result.segments) == 2
        assert result.speaker_count == 2
        assert "SPEAKER_0" in result.speakers
        assert "SPEAKER_1" in result.speakers


class TestAssignSpeakersToTranscript:
    """Tests for speaker assignment to transcript segments."""

    def test_empty_diarization_returns_original(self):
        """Test that original segments are returned when no diarization."""
        transcript_segments = [
            TranscriptSegment(start=0.0, end=2.0, text="Hello"),
        ]
        diarization = DiarizationResult(segments=[], speaker_count=0, speakers=[])

        result = assign_speakers_to_transcript(transcript_segments, diarization)

        assert len(result) == 1
        assert result[0].speaker is None

    def test_assigns_speaker_with_full_overlap(self):
        """Test speaker assignment when diarization fully overlaps."""
        transcript_segments = [
            TranscriptSegment(start=1.0, end=4.0, text="Hello world"),
        ]
        diarization = DiarizationResult(
            segments=[
                DiarizationSegment(start=0.0, end=5.0, speaker="SPEAKER_0"),
            ],
            speaker_count=1,
            speakers=["SPEAKER_0"],
        )

        result = assign_speakers_to_transcript(transcript_segments, diarization)

        assert result[0].speaker == "SPEAKER_0"

    def test_assigns_speaker_with_partial_overlap(self):
        """Test speaker assignment with partial overlap."""
        transcript_segments = [
            TranscriptSegment(start=2.0, end=6.0, text="Hello world"),
        ]
        diarization = DiarizationResult(
            segments=[
                DiarizationSegment(start=0.0, end=4.0, speaker="SPEAKER_0"),  # 2 sec overlap
                DiarizationSegment(start=4.0, end=8.0, speaker="SPEAKER_1"),  # 2 sec overlap
            ],
            speaker_count=2,
            speakers=["SPEAKER_0", "SPEAKER_1"],
        )

        result = assign_speakers_to_transcript(transcript_segments, diarization)

        # Both have equal overlap, first one wins
        assert result[0].speaker in ["SPEAKER_0", "SPEAKER_1"]

    def test_assigns_best_overlapping_speaker(self):
        """Test that speaker with most overlap is assigned."""
        transcript_segments = [
            TranscriptSegment(start=2.0, end=8.0, text="Hello world"),
        ]
        diarization = DiarizationResult(
            segments=[
                DiarizationSegment(start=0.0, end=3.0, speaker="SPEAKER_0"),  # 1 sec overlap
                DiarizationSegment(start=3.0, end=10.0, speaker="SPEAKER_1"),  # 5 sec overlap
            ],
            speaker_count=2,
            speakers=["SPEAKER_0", "SPEAKER_1"],
        )

        result = assign_speakers_to_transcript(transcript_segments, diarization)

        assert result[0].speaker == "SPEAKER_1"

    def test_preserves_segment_text(self):
        """Test that segment text is preserved."""
        transcript_segments = [
            TranscriptSegment(start=0.0, end=2.0, text="Original text"),
        ]
        diarization = DiarizationResult(
            segments=[
                DiarizationSegment(start=0.0, end=5.0, speaker="SPEAKER_0"),
            ],
            speaker_count=1,
            speakers=["SPEAKER_0"],
        )

        result = assign_speakers_to_transcript(transcript_segments, diarization)

        assert result[0].text == "Original text"
        assert result[0].start == 0.0
        assert result[0].end == 2.0

    def test_assigns_speakers_correctly_large_input(self):
        """Test that speaker assignment works correctly with larger inputs (verifying optimization)."""
        # Create 100 transcript segments
        transcript_segments = []
        for i in range(100):
            transcript_segments.append(
                TranscriptSegment(start=float(i), end=float(i + 1), text=f"Text {i}")
            )

        # Create 50 diarization segments (covering every 2 transcript segments)
        diarization_segments = []
        for i in range(50):
            diarization_segments.append(
                DiarizationSegment(start=float(i * 2), end=float(i * 2 + 2), speaker=f"SPEAKER_{i % 2}")
            )

        diarization = DiarizationResult(
            segments=diarization_segments,
            speaker_count=2,
            speakers=["SPEAKER_0", "SPEAKER_1"],
        )

        result = assign_speakers_to_transcript(transcript_segments, diarization)

        assert len(result) == 100
        # Verify first few assignments
        assert result[0].speaker == "SPEAKER_0"  # 0.0-1.0 overlaps with 0.0-2.0 (SPEAKER_0)
        assert result[1].speaker == "SPEAKER_0"  # 1.0-2.0 overlaps with 0.0-2.0 (SPEAKER_0)
        assert result[2].speaker == "SPEAKER_1"  # 2.0-3.0 overlaps with 2.0-4.0 (SPEAKER_1)
        assert result[3].speaker == "SPEAKER_1"  # 3.0-4.0 overlaps with 2.0-4.0 (SPEAKER_1)

        # Verify last few assignments
        assert result[98].speaker == "SPEAKER_1" # 98.0-99.0 overlaps with 98.0-100.0 (SPEAKER_1)
        assert result[99].speaker == "SPEAKER_1" # 99.0-100.0 overlaps with 98.0-100.0 (SPEAKER_1)
