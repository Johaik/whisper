"""Integration tests for the /ingest endpoint."""

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import Recording, RecordingStatus


pytestmark = pytest.mark.integration


class TestIngestEndpoint:
    """Tests for POST /api/v1/ingest endpoint."""

    @pytest.mark.asyncio
    async def test_ingest_requires_auth(self, async_client):
        """Test that ingest endpoint requires authentication."""
        response = await async_client.post("/api/v1/ingest", json={})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_ingest_with_valid_token(self, async_client, auth_headers, fixtures_dir):
        """Test ingest with valid authentication."""
        response = await async_client.post(
            "/api/v1/ingest",
            json={"folder": str(fixtures_dir)},
            headers=auth_headers,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_ingest_nonexistent_folder(self, async_client, auth_headers):
        """Test ingest with nonexistent folder returns 404."""
        response = await async_client.post(
            "/api/v1/ingest",
            json={"folder": "/nonexistent/folder"},
            headers=auth_headers,
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_ingest_discovers_audio_files(self, async_client, auth_headers, async_session):
        """Test that ingest discovers audio files in folder."""
        # Create a temp directory with audio files
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test audio files
            Path(tmpdir, "test1.m4a").write_bytes(b"fake audio 1")
            Path(tmpdir, "test2.wav").write_bytes(b"fake audio 2")
            Path(tmpdir, "not_audio.txt").write_bytes(b"text file")

            response = await async_client.post(
                "/api/v1/ingest",
                json={"folder": tmpdir},
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["discovered"] == 2  # Only audio files
            assert data["queued"] == 2

    @pytest.mark.asyncio
    async def test_ingest_skips_already_processed(self, async_client, auth_headers, async_session):
        """Test that ingest skips already processed files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir, "test.m4a")
            test_file.write_bytes(b"fake audio content")

            # First ingest
            response1 = await async_client.post(
                "/api/v1/ingest",
                json={"folder": tmpdir},
                headers=auth_headers,
            )

            assert response1.json()["discovered"] == 1

            # Second ingest (should skip)
            response2 = await async_client.post(
                "/api/v1/ingest",
                json={"folder": tmpdir},
                headers=auth_headers,
            )

            assert response2.json()["discovered"] == 0
            assert response2.json()["skipped"] == 1

    @pytest.mark.asyncio
    async def test_ingest_reprocesses_failed(self, async_client, auth_headers, async_session):
        """Test that ingest requeues failed recordings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir, "test.m4a")
            test_file.write_bytes(b"fake audio")

            # First ingest
            await async_client.post(
                "/api/v1/ingest",
                json={"folder": tmpdir},
                headers=auth_headers,
            )

            # Mark as failed
            result = await async_session.execute(select(Recording))
            recording = result.scalar_one()
            recording.status = RecordingStatus.FAILED
            await async_session.commit()

            # Re-ingest should requeue (status=QUEUED; periodic task will enqueue)
            response = await async_client.post(
                "/api/v1/ingest",
                json={"folder": tmpdir},
                headers=auth_headers,
            )

            assert response.json()["queued"] == 1

    @pytest.mark.asyncio
    async def test_ingest_force_reprocess(self, async_client, auth_headers, async_session):
        """Test force_reprocess flag requeues all files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir, "test.m4a")
            test_file.write_bytes(b"fake audio")

            # First ingest
            await async_client.post(
                "/api/v1/ingest",
                json={"folder": tmpdir},
                headers=auth_headers,
            )

            # Mark as done
            result = await async_session.execute(select(Recording))
            recording = result.scalar_one()
            recording.status = RecordingStatus.DONE
            await async_session.commit()

            # Force reprocess (status=QUEUED; periodic task will enqueue)
            response = await async_client.post(
                "/api/v1/ingest",
                json={"folder": tmpdir, "force_reprocess": True},
                headers=auth_headers,
            )

            assert response.json()["queued"] == 1

