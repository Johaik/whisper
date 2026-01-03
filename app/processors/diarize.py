"""Speaker diarization using pyannote.audio."""

import logging
from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.processors.transcribe import TranscriptSegment

logger = logging.getLogger(__name__)

# Module-level pipeline cache
_pipeline_cache: dict[str, Any] = {}


@dataclass
class DiarizationSegment:
    """A segment with speaker information."""

    start: float
    end: float
    speaker: str


@dataclass
class DiarizationResult:
    """Result of speaker diarization."""

    segments: list[DiarizationSegment]
    speaker_count: int
    speakers: list[str]


def get_or_load_pipeline() -> Any:
    """Get cached diarization pipeline or load a new one.

    Returns:
        The pyannote diarization Pipeline instance
    """
    settings = get_settings()

    if "pipeline" not in _pipeline_cache:
        if not settings.huggingface_token:
            logger.warning(
                "No HuggingFace token provided. Diarization may fail. "
                "Set HUGGINGFACE_TOKEN environment variable."
            )

        try:
            from pyannote.audio import Pipeline

            logger.info("Loading pyannote speaker diarization pipeline...")
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=settings.huggingface_token,
            )
            _pipeline_cache["pipeline"] = pipeline
            logger.info("Diarization pipeline loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load diarization pipeline: {e}")
            raise

    return _pipeline_cache["pipeline"]


def diarize_audio(audio_path: str) -> DiarizationResult:
    """Run speaker diarization on an audio file.

    Args:
        audio_path: Path to the audio file

    Returns:
        DiarizationResult with speaker segments
    """
    settings = get_settings()

    if not settings.diarization_enabled:
        logger.info("Diarization is disabled in settings")
        return DiarizationResult(segments=[], speaker_count=0, speakers=[])

    logger.info(f"Running diarization on: {audio_path}")

    pipeline = get_or_load_pipeline()
    diarization = pipeline(audio_path)

    segments: list[DiarizationSegment] = []
    speakers_set: set[str] = set()

    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append(
            DiarizationSegment(
                start=turn.start,
                end=turn.end,
                speaker=speaker,
            )
        )
        speakers_set.add(speaker)

    speakers = sorted(speakers_set)

    logger.info(f"Diarization complete: {len(segments)} segments, {len(speakers)} speakers")

    return DiarizationResult(
        segments=segments,
        speaker_count=len(speakers),
        speakers=speakers,
    )


def assign_speakers_to_transcript(
    transcript_segments: list[TranscriptSegment],
    diarization: DiarizationResult,
) -> list[TranscriptSegment]:
    """Assign speakers to transcript segments based on diarization.

    Uses overlap-based assignment: each transcript segment is assigned
    the speaker who has the most overlap with that segment.

    Args:
        transcript_segments: List of transcript segments
        diarization: Diarization result with speaker segments

    Returns:
        Updated transcript segments with speaker assignments
    """
    if not diarization.segments:
        return transcript_segments

    result: list[TranscriptSegment] = []

    for tseg in transcript_segments:
        best_speaker = None
        best_overlap = 0.0

        for dseg in diarization.segments:
            # Calculate overlap
            overlap_start = max(tseg.start, dseg.start)
            overlap_end = min(tseg.end, dseg.end)
            overlap = max(0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = dseg.speaker

        result.append(
            TranscriptSegment(
                start=tseg.start,
                end=tseg.end,
                text=tseg.text,
                speaker=best_speaker,
            )
        )

    return result

