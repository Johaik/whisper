"""Analytics computation from transcription segments."""

import logging
from dataclasses import dataclass
from typing import Any

from app.processors.transcribe import TranscriptSegment

logger = logging.getLogger(__name__)


@dataclass
class AnalyticsResult:
    """Computed analytics for a recording."""

    total_speech_time: float
    total_silence_time: float
    talk_time_ratio: float
    silence_ratio: float
    segment_count: int
    avg_segment_length: float
    speaker_count: int
    speaker_turns: int
    long_silence_count: int
    long_silence_threshold_sec: float
    speaker_talk_times: dict[str, float]
    analytics_json: dict[str, Any]


def compute_analytics(
    segments: list[TranscriptSegment],
    total_duration: float | None,
    long_silence_threshold: float = 5.0,
) -> AnalyticsResult:
    """Compute analytics from transcript segments.

    Args:
        segments: List of transcript segments with timing
        total_duration: Total duration of the audio in seconds
        long_silence_threshold: Threshold for counting long silences (seconds)

    Returns:
        AnalyticsResult with computed metrics
    """
    if not segments:
        return AnalyticsResult(
            total_speech_time=0.0,
            total_silence_time=total_duration or 0.0,
            talk_time_ratio=0.0,
            silence_ratio=1.0 if total_duration else 0.0,
            segment_count=0,
            avg_segment_length=0.0,
            speaker_count=0,
            speaker_turns=0,
            long_silence_count=0,
            long_silence_threshold_sec=long_silence_threshold,
            speaker_talk_times={},
            analytics_json={},
        )

    # Calculate speech time
    total_speech_time = sum(seg.end - seg.start for seg in segments)

    # Calculate silence time (gaps between segments)
    silence_times: list[float] = []
    sorted_segments = sorted(segments, key=lambda s: s.start)

    # Silence before first segment
    if sorted_segments[0].start > 0:
        silence_times.append(sorted_segments[0].start)

    # Gaps between segments
    for i in range(1, len(sorted_segments)):
        gap = sorted_segments[i].start - sorted_segments[i - 1].end
        if gap > 0:
            silence_times.append(gap)

    # Silence after last segment
    if total_duration and sorted_segments[-1].end < total_duration:
        silence_times.append(total_duration - sorted_segments[-1].end)

    total_silence_time = sum(silence_times)

    # Use calculated total if duration not provided
    effective_duration = total_duration or (total_speech_time + total_silence_time)

    if effective_duration > 0:
        talk_time_ratio = total_speech_time / effective_duration
        silence_ratio = total_silence_time / effective_duration
    else:
        talk_time_ratio = 0.0
        silence_ratio = 0.0

    # Segment statistics
    segment_count = len(segments)
    avg_segment_length = total_speech_time / segment_count if segment_count > 0 else 0.0

    # Speaker statistics
    speakers: set[str] = set()
    speaker_talk_times: dict[str, float] = {}
    speaker_turns = 0
    last_speaker: str | None = None
    segment_lengths: list[float] = []

    for seg in sorted_segments:
        duration = seg.end - seg.start
        segment_lengths.append(round(duration, 2))

        if seg.speaker:
            speakers.add(seg.speaker)
            speaker_talk_times[seg.speaker] = speaker_talk_times.get(seg.speaker, 0) + duration

            if seg.speaker != last_speaker:
                speaker_turns += 1
                last_speaker = seg.speaker

    # Count long silences and build silence lists
    long_silence_count = 0
    silence_lengths: list[float] = []
    long_silences: list[float] = []

    for s in silence_times:
        rounded_s = round(s, 2)
        silence_lengths.append(rounded_s)
        if s >= long_silence_threshold:
            long_silence_count += 1
            long_silences.append(rounded_s)

    # Build analytics JSON
    analytics_json: dict[str, Any] = {
        "speech_time_sec": round(total_speech_time, 2),
        "silence_time_sec": round(total_silence_time, 2),
        "effective_duration_sec": round(effective_duration, 2),
        "segment_lengths": segment_lengths,
        "silence_lengths": silence_lengths,
        "speaker_talk_times": {k: round(v, 2) for k, v in speaker_talk_times.items()},
        "long_silences": long_silences,
    }

    logger.info(
        f"Analytics computed: {segment_count} segments, "
        f"speech={total_speech_time:.1f}s, silence={total_silence_time:.1f}s, "
        f"speakers={len(speakers)}, turns={speaker_turns}"
    )

    return AnalyticsResult(
        total_speech_time=total_speech_time,
        total_silence_time=total_silence_time,
        talk_time_ratio=talk_time_ratio,
        silence_ratio=silence_ratio,
        segment_count=segment_count,
        avg_segment_length=avg_segment_length,
        speaker_count=len(speakers),
        speaker_turns=speaker_turns,
        long_silence_count=long_silence_count,
        long_silence_threshold_sec=long_silence_threshold,
        speaker_talk_times=speaker_talk_times,
        analytics_json=analytics_json,
    )

