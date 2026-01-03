"""Unit tests for the analytics processor."""

import pytest

from app.processors.analytics import AnalyticsResult, compute_analytics
from app.processors.transcribe import TranscriptSegment


class TestComputeAnalytics:
    """Tests for compute_analytics function."""

    def test_empty_segments(self):
        """Test analytics with no segments."""
        result = compute_analytics(segments=[], total_duration=60.0)

        assert result.total_speech_time == 0.0
        assert result.total_silence_time == 60.0
        assert result.talk_time_ratio == 0.0
        assert result.silence_ratio == 1.0
        assert result.segment_count == 0

    def test_empty_segments_no_duration(self):
        """Test analytics with no segments and no duration."""
        result = compute_analytics(segments=[], total_duration=None)

        assert result.total_speech_time == 0.0
        assert result.total_silence_time == 0.0
        assert result.segment_count == 0

    def test_single_segment(self):
        """Test analytics with a single segment."""
        segments = [
            TranscriptSegment(start=10.0, end=20.0, text="Hello"),
        ]
        result = compute_analytics(segments=segments, total_duration=60.0)

        assert result.total_speech_time == 10.0
        assert result.total_silence_time == 50.0  # 10s before + 40s after
        assert result.talk_time_ratio == pytest.approx(10.0 / 60.0)
        assert result.silence_ratio == pytest.approx(50.0 / 60.0)
        assert result.segment_count == 1
        assert result.avg_segment_length == 10.0

    def test_multiple_segments(self, sample_segments):
        """Test analytics with multiple segments."""
        result = compute_analytics(segments=sample_segments, total_duration=10.0)

        # Speech: 2.5 + 2.0 + 2.5 = 7.0 seconds
        assert result.total_speech_time == 7.0
        assert result.segment_count == 3
        assert result.avg_segment_length == pytest.approx(7.0 / 3)

    def test_speaker_count(self, sample_segments):
        """Test that speaker count is calculated."""
        result = compute_analytics(segments=sample_segments, total_duration=10.0)

        assert result.speaker_count == 2  # SPEAKER_0 and SPEAKER_1

    def test_speaker_turns(self, sample_segments):
        """Test speaker turn counting."""
        result = compute_analytics(segments=sample_segments, total_duration=10.0)

        # SPEAKER_0 -> SPEAKER_1 -> SPEAKER_0 = 3 turns
        assert result.speaker_turns == 3

    def test_long_silence_detection(self):
        """Test long silence counting."""
        segments = [
            TranscriptSegment(start=0.0, end=2.0, text="Hello"),
            TranscriptSegment(start=10.0, end=12.0, text="World"),  # 8 sec gap
            TranscriptSegment(start=14.0, end=16.0, text="Test"),  # 2 sec gap
        ]
        result = compute_analytics(
            segments=segments,
            total_duration=25.0,  # 9s at end (16 to 25)
            long_silence_threshold=5.0,
        )

        assert result.long_silence_count == 2  # 8s gap + 9s at end
        assert result.long_silence_threshold_sec == 5.0

    def test_no_long_silences(self, sample_segments):
        """Test when no silences exceed threshold."""
        result = compute_analytics(
            segments=sample_segments,
            total_duration=8.0,
            long_silence_threshold=10.0,
        )

        assert result.long_silence_count == 0

    def test_analytics_json_contains_details(self, sample_segments):
        """Test that analytics_json contains detailed info."""
        result = compute_analytics(segments=sample_segments, total_duration=10.0)

        assert "speech_time_sec" in result.analytics_json
        assert "silence_time_sec" in result.analytics_json
        assert "segment_lengths" in result.analytics_json
        assert "silence_lengths" in result.analytics_json
        assert "speaker_talk_times" in result.analytics_json

    def test_speaker_talk_times(self, sample_segments):
        """Test speaker talk time calculation."""
        result = compute_analytics(segments=sample_segments, total_duration=10.0)

        # SPEAKER_0: 2.5 + 2.5 = 5.0
        # SPEAKER_1: 2.0
        assert "SPEAKER_0" in result.speaker_talk_times
        assert "SPEAKER_1" in result.speaker_talk_times
        assert result.speaker_talk_times["SPEAKER_0"] == 5.0
        assert result.speaker_talk_times["SPEAKER_1"] == 2.0

    def test_segments_without_speakers(self):
        """Test analytics with segments that have no speaker info."""
        segments = [
            TranscriptSegment(start=0.0, end=5.0, text="Hello"),
            TranscriptSegment(start=5.0, end=10.0, text="World"),
        ]
        result = compute_analytics(segments=segments, total_duration=10.0)

        assert result.speaker_count == 0
        assert result.speaker_turns == 0
        assert result.speaker_talk_times == {}

    def test_infers_duration_from_segments(self):
        """Test that duration is inferred when not provided."""
        segments = [
            TranscriptSegment(start=0.0, end=5.0, text="Hello"),
            TranscriptSegment(start=7.0, end=10.0, text="World"),
        ]
        result = compute_analytics(segments=segments, total_duration=None)

        # Speech: 5 + 3 = 8, Silence: 2 (gap)
        assert result.total_speech_time == 8.0
        assert result.total_silence_time == 2.0
        assert result.talk_time_ratio == pytest.approx(8.0 / 10.0)

    def test_consecutive_same_speaker_no_extra_turns(self):
        """Test that consecutive segments from same speaker don't add turns."""
        segments = [
            TranscriptSegment(start=0.0, end=2.0, text="A", speaker="SPEAKER_0"),
            TranscriptSegment(start=2.0, end=4.0, text="B", speaker="SPEAKER_0"),
            TranscriptSegment(start=4.0, end=6.0, text="C", speaker="SPEAKER_0"),
        ]
        result = compute_analytics(segments=segments, total_duration=6.0)

        assert result.speaker_turns == 1  # Same speaker throughout

