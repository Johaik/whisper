"""Audio transcription processor using faster-whisper."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

# Module-level model cache for reuse across tasks
_model_cache: dict[str, Any] = {}


@dataclass
class TranscriptSegment:
    """A single segment of transcription."""

    start: float
    end: float
    text: str
    speaker: str | None = None


@dataclass
class TranscriptionResult:
    """Result of audio transcription."""

    text: str
    segments: list[TranscriptSegment]
    language: str
    language_probability: float
    model_name: str
    beam_size: int
    compute_type: str


def get_or_load_model(
    model_name: str | None = None,
    device: str | None = None,
    compute_type: str | None = None,
) -> Any:
    """Get cached model or load a new one.

    Args:
        model_name: Name of the Whisper model
        device: Device to use (cpu or cuda)
        compute_type: Compute type (int8, float16, float32)

    Returns:
        The loaded WhisperModel instance
    """
    from faster_whisper import WhisperModel

    settings = get_settings()
    model_name = model_name or settings.model_name
    device = device or settings.device
    compute_type = compute_type or settings.compute_type

    cache_key = f"{model_name}:{device}:{compute_type}"

    if cache_key not in _model_cache:
        logger.info(f"Loading Whisper model: {model_name} on {device} with {compute_type}")
        _model_cache[cache_key] = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
        )
        logger.info(f"Model loaded successfully: {model_name}")

    return _model_cache[cache_key]


def transcribe_audio(
    audio_path: str,
    model_name: str | None = None,
    beam_size: int | None = None,
    vad_filter: bool | None = None,
    vad_min_silence_ms: int | None = None,
    device: str | None = None,
    compute_type: str | None = None,
    progress_callback: Callable[[int], None] | None = None,
) -> TranscriptionResult:
    """Transcribe audio file using faster-whisper.

    Args:
        audio_path: Path to the audio file
        model_name: Whisper model name (defaults to config)
        beam_size: Beam size for decoding
        vad_filter: Whether to use VAD filtering
        vad_min_silence_ms: Minimum silence duration for VAD
        device: Device to use (cpu or cuda)
        compute_type: Compute type

    Returns:
        TranscriptionResult with full text and segments
    """
    settings = get_settings()

    # Use settings defaults if not provided
    model_name = model_name or settings.model_name
    beam_size = beam_size if beam_size is not None else settings.beam_size
    vad_filter = vad_filter if vad_filter is not None else settings.vad_filter
    vad_min_silence_ms = vad_min_silence_ms or settings.vad_min_silence_ms
    device = device or settings.device
    compute_type = compute_type or settings.compute_type

    logger.info(f"Transcribing: {audio_path}")

    model = get_or_load_model(model_name, device, compute_type)

    # Build VAD parameters
    vad_parameters = None
    if vad_filter:
        vad_parameters = {"min_silence_duration_ms": vad_min_silence_ms}

    # Run transcription
    segments_iter, info = model.transcribe(
        audio_path,
        language="he",
        beam_size=beam_size,
        vad_filter=vad_filter,
        vad_parameters=vad_parameters,
    )

    # Collect all segments
    segments: list[TranscriptSegment] = []
    texts: list[str] = []

    for segment in segments_iter:
        segments.append(
            TranscriptSegment(
                start=segment.start,
                end=segment.end,
                text=segment.text.strip(),
            )
        )
        texts.append(segment.text.strip())
        if progress_callback is not None:
            progress_callback(len(segments))

    full_text = " ".join(texts)

    logger.info(
        f"Transcription complete: {len(segments)} segments, "
        f"language={info.language} ({info.language_probability:.1%})"
    )

    return TranscriptionResult(
        text=full_text,
        segments=segments,
        language=info.language,
        language_probability=info.language_probability,
        model_name=model_name,
        beam_size=beam_size,
        compute_type=compute_type,
    )


def segments_to_json(segments: list[TranscriptSegment]) -> list[dict[str, Any]]:
    """Convert segments to JSON-serializable format.

    Args:
        segments: List of TranscriptSegment objects

    Returns:
        List of dictionaries
    """
    return [
        {
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
            "speaker": seg.speaker,
        }
        for seg in segments
    ]

