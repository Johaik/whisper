"""Application configuration using pydantic settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # API settings
    api_token: str = "dev-token-change-me"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Database settings
    database_url: str = "postgresql+asyncpg://whisper:whisper@localhost:5432/whisper"
    database_url_sync: str = "postgresql://whisper:whisper@localhost:5432/whisper"

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
    task_timeout_seconds: int = 1800  # 30 minutes
    task_max_retries: int = 3

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

