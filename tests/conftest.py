"""Shared test fixtures and configuration."""

import socket
import tempfile
import uuid
import sys
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
import os

import pytest
import pytest_asyncio
import sqlalchemy
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

# ============================================
# Database Patching
# ============================================

def _is_postgres_available():
    """Check if Postgres is available."""
    try:
        sock = socket.create_connection(("localhost", 5433), timeout=1)
        sock.close()
        return True
    except (OSError, socket.timeout):
        return False

# Use SQLite if Postgres is not available
USE_SQLITE = not _is_postgres_available()

if USE_SQLITE:
    print("WARNING: Postgres not available. Patching SQLAlchemy to use SQLite for tests.")

    from sqlalchemy.dialects import postgresql
    from sqlalchemy.types import JSON
    import sqlalchemy.types as types

    # Patch JSONB -> JSON
    class MockJSONB(types.TypeDecorator):
        impl = types.JSON
        cache_ok = True
        def load_dialect_impl(self, dialect):
            return dialect.type_descriptor(types.JSON())

    postgresql.JSONB = MockJSONB

    # Patch UUID -> Uuid
    # Uuid in SQLAlchemy 2.0 works with both native UUID and char/binary fallback
    postgresql.UUID = types.Uuid

# ============================================
# Application Imports (Must be after patching)
# ============================================

# Ensure API_TOKEN is set before importing app.main, which instantiates Settings
os.environ["API_TOKEN"] = "test-token"

from app.config import Settings, get_settings
from app.db.models import Base, Enrichment, Recording, RecordingStatus, Transcript
from app.main import app
from app.processors.transcribe import TranscriptSegment


# ============================================
# Test Settings
# ============================================

def get_test_settings() -> Settings:
    """Get test-specific settings."""
    if USE_SQLITE:
        # Use in-memory SQLite
        db_url_sync = "sqlite:///file:testdb?mode=memory&cache=shared&uri=true"
        db_url_async = "sqlite+aiosqlite:///file:testdb?mode=memory&cache=shared&uri=true"
    else:
        # Short timeouts so tests fail fast when Postgres/Redis are not running
        db_url_sync = "postgresql://whisper_test:whisper_test@localhost:5433/whisper_test?connect_timeout=3"
        db_url_async = "postgresql+asyncpg://whisper_test:whisper_test@localhost:5433/whisper_test"

    return Settings(
        api_token="test-token",
        database_url=db_url_async,
        database_url_sync=db_url_sync,
        redis_url="redis://localhost:6380/0",
        calls_dir=str(Path(__file__).parent / "fixtures"),
        output_dir="/tmp/whisper_test_outputs",
        diarization_enabled=False,
        heartbeat_interval_sec=0,  # Disable heartbeat in tests to avoid thread/DB contention
    )


@pytest.fixture
def test_settings() -> Settings:
    """Provide test settings."""
    return get_test_settings()


# ============================================
# Database Fixtures
# ============================================


def _test_db_reachable() -> bool:
    """Return True if test Postgres (localhost:5433) is reachable within 2s."""
    if USE_SQLITE:
        return True
    try:
        sock = socket.create_connection(("localhost", 5433), timeout=2)
        sock.close()
        return True
    except (OSError, socket.timeout):
        return False


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Provide a sync database session with clean tables for each test."""
    if not _test_db_reachable():
        pytest.skip("Test Postgres not reachable at localhost:5433 (start test DB or skip)")
    settings = get_test_settings()

    connect_args = {}
    if USE_SQLITE:
        connect_args = {"check_same_thread": False}

    engine = create_engine(
        settings.database_url_sync,
        echo=False,
        pool_pre_ping=True,
        connect_args=connect_args
    )

    # Create all tables fresh for this test
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Create session
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    if USE_SQLITE:
        # Enable foreign keys for SQLite
        session.execute(text("PRAGMA foreign_keys=ON"))

    yield session

    # Cleanup
    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_engine():
    """Create async database engine for tests."""
    if not _test_db_reachable():
        pytest.skip("Test Postgres not reachable at localhost:5433 (start test DB or skip)")
    settings = get_test_settings()

    connect_args = {}
    if USE_SQLITE:
        connect_args = {"check_same_thread": False}

    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        connect_args=connect_args
    )
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    if USE_SQLITE:
        async with engine.connect() as conn:
            await conn.execute(text("PRAGMA foreign_keys=ON"))

    yield engine
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide an async database session."""
    async_session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session


# ============================================
# Sample Data Fixtures
# ============================================

@pytest.fixture
def sample_recording(db_session: Session) -> Recording:
    """Create a sample recording in the database."""
    recording = Recording(
        id=uuid.uuid4(),
        file_path="/data/calls/test_audio.m4a",
        file_name="test_audio.m4a",
        file_hash="abc123def456",
        file_size=1024000,
        status=RecordingStatus.DISCOVERED,
        duration_sec=60.0,
        sample_rate=44100,
        channels=2,
        codec="aac",
        container="m4a",
    )
    db_session.add(recording)
    db_session.commit()
    db_session.refresh(recording)
    return recording


@pytest.fixture
def processed_recording(db_session: Session) -> Recording:
    """Create a fully processed recording with transcript and enrichment."""
    recording = Recording(
        id=uuid.uuid4(),
        file_path="/data/calls/processed_audio.m4a",
        file_name="processed_audio.m4a",
        file_hash="processed123",
        file_size=2048000,
        status=RecordingStatus.DONE,
        duration_sec=120.0,
        sample_rate=44100,
        channels=2,
        codec="aac",
        container="m4a",
        processed_at=datetime.now(timezone.utc),
    )
    db_session.add(recording)
    db_session.flush()

    transcript = Transcript(
        recording_id=recording.id,
        model_name="ivrit-ai/whisper-large-v3-turbo-ct2",
        beam_size=5,
        compute_type="int8",
        language="he",
        language_probability=0.98,
        text="זה טקסט לדוגמה בעברית",
        segments_json=[
            {"start": 0.0, "end": 2.0, "text": "זה טקסט", "speaker": "SPEAKER_0"},
            {"start": 2.0, "end": 4.0, "text": "לדוגמה בעברית", "speaker": "SPEAKER_1"},
        ],
    )
    db_session.add(transcript)

    enrichment = Enrichment(
        recording_id=recording.id,
        speaker_count=2,
        diarization_enabled=True,
        total_speech_time=4.0,
        total_silence_time=116.0,
        talk_time_ratio=0.033,
        silence_ratio=0.967,
        segment_count=2,
        avg_segment_length=2.0,
        speaker_turns=2,
    )
    db_session.add(enrichment)

    db_session.commit()
    db_session.refresh(recording)
    return recording


@pytest.fixture
def sample_segments() -> list[TranscriptSegment]:
    """Provide sample transcript segments for testing."""
    return [
        TranscriptSegment(start=0.0, end=2.5, text="Hello world", speaker="SPEAKER_0"),
        TranscriptSegment(start=3.0, end=5.0, text="Testing one two", speaker="SPEAKER_1"),
        TranscriptSegment(start=5.5, end=8.0, text="Three four five", speaker="SPEAKER_0"),
    ]


# ============================================
# Mock Fixtures
# ============================================

@pytest.fixture
def mock_whisper_model():
    """Mock the faster-whisper model."""
    mock_model = MagicMock()

    # Create mock segment objects
    mock_segment_1 = MagicMock()
    mock_segment_1.start = 0.0
    mock_segment_1.end = 2.0
    mock_segment_1.text = "שלום עולם"

    mock_segment_2 = MagicMock()
    mock_segment_2.start = 2.5
    mock_segment_2.end = 5.0
    mock_segment_2.text = "זה טקסט לבדיקה"

    mock_info = MagicMock()
    mock_info.language = "he"
    mock_info.language_probability = 0.95

    mock_model.transcribe.return_value = (
        iter([mock_segment_1, mock_segment_2]),
        mock_info,
    )

    return mock_model


@pytest.fixture
def mock_ffprobe_output() -> dict[str, Any]:
    """Provide mock ffprobe JSON output."""
    return {
        "format": {
            "filename": "/data/calls/test.m4a",
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "duration": "60.123456",
            "bit_rate": "128000",
        },
        "streams": [
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "44100",
                "channels": 2,
            }
        ],
    }


# ============================================
# API Client Fixtures
# ============================================

@pytest.fixture
def test_client() -> Generator[TestClient, None, None]:
    """Provide a test client for sync API testing."""
    app.dependency_overrides[get_settings] = get_test_settings
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Provide authentication headers."""
    return {"Authorization": "Bearer test-token"}


@pytest_asyncio.fixture
async def async_client(async_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async test client."""
    from app.db.session import get_async_session

    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_settings] = get_test_settings
    app.dependency_overrides[get_async_session] = override_get_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


# ============================================
# Temporary File Fixtures
# ============================================

@pytest.fixture
def temp_audio_file() -> Generator[Path, None, None]:
    """Create a temporary audio file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        # Write minimal WAV header (44 bytes) + some data
        # RIFF header
        f.write(b"RIFF")
        f.write((36 + 1000).to_bytes(4, "little"))  # File size - 8
        f.write(b"WAVE")
        # fmt chunk
        f.write(b"fmt ")
        f.write((16).to_bytes(4, "little"))  # Chunk size
        f.write((1).to_bytes(2, "little"))  # Audio format (PCM)
        f.write((1).to_bytes(2, "little"))  # Channels
        f.write((44100).to_bytes(4, "little"))  # Sample rate
        f.write((88200).to_bytes(4, "little"))  # Byte rate
        f.write((2).to_bytes(2, "little"))  # Block align
        f.write((16).to_bytes(2, "little"))  # Bits per sample
        # data chunk
        f.write(b"data")
        f.write((1000).to_bytes(4, "little"))  # Data size
        f.write(b"\x00" * 1000)  # Silence
        temp_path = Path(f.name)

    yield temp_path
    temp_path.unlink(missing_ok=True)


@pytest.fixture
def fixtures_dir() -> Path:
    """Get the fixtures directory path."""
    fixtures = Path(__file__).parent / "fixtures"
    fixtures.mkdir(exist_ok=True)
    return fixtures
