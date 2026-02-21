"""Application configuration using pydantic settings."""

from functools import lru_cache
from typing import Any, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # API settings
    api_token: str
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    @field_validator("api_token")
    @classmethod
    def validate_api_token(cls, v: str) -> str:
        """Validate API token security."""
        if not v or not v.strip():
            raise ValueError("API token cannot be empty")
        if v == "dev-token-change-me":
            raise ValueError("API token cannot be the default insecure value. Please set a secure API_TOKEN.")
        return v

    # Database settings
    database_url: str
    database_url_sync: str

    # Redis settings
    redis_url: str = "redis://localhost:6379/0"

    # File paths
    calls_dir: str = "/data/calls"
    output_dir: str = "/data/outputs"

    # Whisper model settings
    model_name: str = "ivrit-ai/whisper-large-v3-turbo-ct2"
    device: Literal["cpu", "cuda"] = "cpu"
    compute_type: Literal["int8", "float16", "float32"] = "int8"
    beam_size: int = 5
    vad_filter: bool = True
    vad_min_silence_ms: int = 500

    # Diarization settings
    diarization_enabled: bool = True
    diarization_max_duration_sec: int = 600  # Skip diarization for calls > 10 minutes
    huggingface_token: str | None = None  # Required for pyannote

    # Worker settings
    worker_concurrency: int = 1
    # Task time limit (seconds). None or 0 = no limit (long processes allowed). Stuck = no heartbeat, not timeout.
    task_timeout_seconds: int | None = None
    task_max_retries: int = 3
    # Stuck = no progress (no heartbeat) for this many seconds. Default 15 min.
    stuck_processing_threshold_sec: int = 900
    # Heartbeat interval: update recording.updated_at every N sec while processing so we detect stuck vs slow.
    heartbeat_interval_sec: int = 120

    @field_validator("task_timeout_seconds", mode="before")
    @classmethod
    def coerce_task_timeout(cls, v: Any) -> int | None:
        """Coerce empty or 0 to None = no task time limit (long processes allowed)."""
        if v is None:
            return None
        if isinstance(v, str) and v.strip() == "":
            return None
        n = int(v) if isinstance(v, str) else v
        return None if n == 0 else n

    # Audio file extensions to process
    audio_extensions: tuple[str, ...] = (".m4a", ".mp3", ".wav", ".aac", ".ogg", ".flac")

    # Watcher settings
    watcher_enabled: bool = True
    watcher_poll_interval: int = 30  # seconds between folder scans
    watcher_stable_seconds: int = 10  # file must be unmodified for this long

    # Source sync settings (for Google Drive integration)
    sync_enabled: bool = False  # Enable automatic syncing from source folder
    source_dir: str = "/data/source"  # Source folder (Google Drive mount)
    sync_batch_size: int = 20  # Number of files to copy per batch

    # Google Contacts API settings (optional, for caller name lookup)
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_refresh_token: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

