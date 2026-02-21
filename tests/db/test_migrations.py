"""Tests for Alembic migrations."""

import os
import socket

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text


pytestmark = pytest.mark.db


def _test_db_reachable() -> bool:
    """Return True if test Postgres (localhost:5433) is reachable within 2s."""
    try:
        sock = socket.create_connection(("localhost", 5433), timeout=2)
        sock.close()
        return True
    except (OSError, socket.timeout):
        return False


class TestMigrations:
    """Tests for database migrations."""

    @pytest.fixture(autouse=True)
    def setup_env(self, test_settings):
        """Set environment variable for Alembic migrations."""
        if not _test_db_reachable():
            pytest.skip("Test Postgres not reachable at localhost:5433 (start test DB or skip)")
        old_value = os.environ.get("DATABASE_URL_SYNC")
        os.environ["DATABASE_URL_SYNC"] = test_settings.database_url_sync
        yield
        if old_value is not None:
            os.environ["DATABASE_URL_SYNC"] = old_value
        else:
            os.environ.pop("DATABASE_URL_SYNC", None)

    @pytest.fixture
    def alembic_config(self, test_settings):
        """Create Alembic config for testing."""
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", test_settings.database_url_sync)
        return config

    @pytest.fixture
    def fresh_engine(self, test_settings):
        """Create a fresh database engine."""
        engine = create_engine(test_settings.database_url_sync)
        # Drop all tables to start fresh
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS enrichments CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS transcripts CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS recordings CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE"))
            conn.execute(text("DROP TYPE IF EXISTS recordingstatus CASCADE"))
            conn.commit()
        yield engine
        # Cleanup after test
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS enrichments CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS transcripts CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS recordings CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE"))
            conn.execute(text("DROP TYPE IF EXISTS recordingstatus CASCADE"))
            conn.commit()
        engine.dispose()

    def test_upgrade_creates_all_tables(self, alembic_config, fresh_engine):
        """Test that upgrade creates all required tables."""
        command.upgrade(alembic_config, "head")

        inspector = inspect(fresh_engine)
        tables = inspector.get_table_names()

        assert "recordings" in tables
        assert "transcripts" in tables
        assert "enrichments" in tables
        assert "alembic_version" in tables

    def test_recordings_table_has_correct_columns(self, alembic_config, fresh_engine):
        """Test that recordings table has all expected columns."""
        command.upgrade(alembic_config, "head")

        inspector = inspect(fresh_engine)
        columns = {col["name"] for col in inspector.get_columns("recordings")}

        expected_columns = {
            "id",
            "file_path",
            "file_name",
            "file_hash",
            "file_size",
            "status",
            "error_message",
            "retry_count",
            "processing_segments_count",
            "processing_step",
            "processing_step_started_at",
            "duration_sec",
            "sample_rate",
            "channels",
            "codec",
            "container",
            "bit_rate",
            "metadata_json",
            "created_at",
            "updated_at",
            "processed_at",
        }

        assert expected_columns.issubset(columns)

    def test_recordings_table_has_correct_indexes(self, alembic_config, fresh_engine):
        """Test that recordings table has required indexes."""
        command.upgrade(alembic_config, "head")

        inspector = inspect(fresh_engine)
        indexes = {idx["name"] for idx in inspector.get_indexes("recordings")}

        # Should have indexes on file_path and status
        assert any("file_path" in idx for idx in indexes)
        assert any("status" in idx for idx in indexes)

    def test_transcripts_table_has_correct_columns(self, alembic_config, fresh_engine):
        """Test that transcripts table has all expected columns."""
        command.upgrade(alembic_config, "head")

        inspector = inspect(fresh_engine)
        columns = {col["name"] for col in inspector.get_columns("transcripts")}

        expected_columns = {
            "id",
            "recording_id",
            "model_name",
            "beam_size",
            "compute_type",
            "language",
            "language_probability",
            "text",
            "segments_json",
            "transcript_json",
            "created_at",
        }

        assert expected_columns.issubset(columns)

    def test_enrichments_table_has_correct_columns(self, alembic_config, fresh_engine):
        """Test that enrichments table has all expected columns."""
        command.upgrade(alembic_config, "head")

        inspector = inspect(fresh_engine)
        columns = {col["name"] for col in inspector.get_columns("enrichments")}

        expected_columns = {
            "id",
            "recording_id",
            "speaker_count",
            "diarization_enabled",
            "total_speech_time",
            "total_silence_time",
            "talk_time_ratio",
            "silence_ratio",
            "segment_count",
            "avg_segment_length",
            "speaker_turns",
            "long_silence_count",
            "long_silence_threshold_sec",
            "analytics_json",
            "created_at",
        }

        assert expected_columns.issubset(columns)

    def test_foreign_keys_exist(self, alembic_config, fresh_engine):
        """Test that foreign keys are created."""
        command.upgrade(alembic_config, "head")

        inspector = inspect(fresh_engine)

        # Check transcripts FK
        transcripts_fks = inspector.get_foreign_keys("transcripts")
        assert len(transcripts_fks) == 1
        assert transcripts_fks[0]["referred_table"] == "recordings"

        # Check enrichments FK
        enrichments_fks = inspector.get_foreign_keys("enrichments")
        assert len(enrichments_fks) == 1
        assert enrichments_fks[0]["referred_table"] == "recordings"

    def test_unique_constraints_exist(self, alembic_config, fresh_engine):
        """Test that unique constraints are created."""
        command.upgrade(alembic_config, "head")

        inspector = inspect(fresh_engine)

        # Check file_hash unique constraint
        recordings_unique = inspector.get_unique_constraints("recordings")
        file_hash_unique = [c for c in recordings_unique if "file_hash" in c.get("column_names", [])]
        assert len(file_hash_unique) == 1

    def test_downgrade_removes_tables(self, alembic_config, fresh_engine):
        """Test that downgrade removes tables."""
        # First upgrade
        command.upgrade(alembic_config, "head")

        # Then downgrade
        command.downgrade(alembic_config, "base")

        inspector = inspect(fresh_engine)
        tables = inspector.get_table_names()

        assert "recordings" not in tables
        assert "transcripts" not in tables
        assert "enrichments" not in tables

    def test_revision_order(self, alembic_config):
        """Test that migrations have proper revision order."""
        script_dir = ScriptDirectory.from_config(alembic_config)
        revisions = list(script_dir.walk_revisions())

        # Should have at least the initial migration
        assert len(revisions) >= 1

        # First revision should have no down_revision
        base_revision = [r for r in revisions if r.down_revision is None]
        assert len(base_revision) == 1
