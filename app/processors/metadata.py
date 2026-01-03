"""Audio metadata extraction using ffprobe."""

import hashlib
import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AudioMetadata:
    """Metadata extracted from an audio file."""

    duration_sec: float | None
    sample_rate: int | None
    channels: int | None
    codec: str | None
    container: str | None
    bit_rate: int | None
    file_size: int
    file_hash: str
    raw_metadata: dict[str, Any]


def compute_file_hash(file_path: str, chunk_size: int = 8192) -> str:
    """Compute SHA256 hash of a file.

    Args:
        file_path: Path to the file
        chunk_size: Size of chunks to read

    Returns:
        Hex-encoded SHA256 hash
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def extract_metadata(audio_path: str) -> AudioMetadata:
    """Extract metadata from an audio file using ffprobe.

    Args:
        audio_path: Path to the audio file

    Returns:
        AudioMetadata with extracted information

    Raises:
        FileNotFoundError: If the audio file doesn't exist
        RuntimeError: If ffprobe fails
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    file_size = path.stat().st_size
    file_hash = compute_file_hash(audio_path)

    logger.info(f"Extracting metadata from: {audio_path}")

    # Run ffprobe
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        audio_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        probe_data = json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"ffprobe failed: {e.stderr}")
        raise RuntimeError(f"ffprobe failed for {audio_path}: {e.stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffprobe timed out for {audio_path}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse ffprobe output: {e}")

    # Extract format info
    format_info = probe_data.get("format", {})
    duration_sec = float(format_info.get("duration", 0)) or None
    container = format_info.get("format_name")
    bit_rate = int(format_info.get("bit_rate", 0)) or None

    # Find the audio stream
    audio_stream = None
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") == "audio":
            audio_stream = stream
            break

    if audio_stream:
        sample_rate = int(audio_stream.get("sample_rate", 0)) or None
        channels = audio_stream.get("channels")
        codec = audio_stream.get("codec_name")
    else:
        sample_rate = None
        channels = None
        codec = None

    logger.info(
        f"Metadata extracted: duration={duration_sec}s, "
        f"sample_rate={sample_rate}, channels={channels}, codec={codec}"
    )

    return AudioMetadata(
        duration_sec=duration_sec,
        sample_rate=sample_rate,
        channels=channels,
        codec=codec,
        container=container,
        bit_rate=bit_rate,
        file_size=file_size,
        file_hash=file_hash,
        raw_metadata=probe_data,
    )

