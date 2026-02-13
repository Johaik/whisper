"""Integration tests for the /recordings endpoints."""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.db.models import Recording, RecordingStatus


pytestmark = pytest.mark.integration


class TestListRecordings:
    """Tests for GET /api/v1/recordings endpoint."""

    @pytest.mark.asyncio
    async def test_list_requires_auth(self, async_client):
        """Test that list endpoint requires authentication."""
        response = await async_client.get("/api/v1/recordings")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_empty(self, async_client, auth_headers):
        """Test listing when no recordings exist."""
        response = await async_client.get(
            "/api/v1/recordings",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_with_recordings(self, async_client, auth_headers, async_session):
        """Test listing recordings."""
        # Create test recordings
        for i in range(3):
            recording = Recording(
                file_path=f"/data/calls/test{i}.m4a",
                file_name=f"test{i}.m4a",
                file_hash=f"hash{i}",
                file_size=1000 * (i + 1),
                status=RecordingStatus.DISCOVERED,
            )
            async_session.add(recording)
        await async_session.commit()

        response = await async_client.get(
            "/api/v1/recordings",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert data["total"] == 3

    @pytest.mark.asyncio
    async def test_list_with_status_filter(self, async_client, auth_headers, async_session):
        """Test filtering by status."""
        # Create recordings with different statuses
        statuses = [RecordingStatus.DISCOVERED, RecordingStatus.DONE, RecordingStatus.FAILED]
        for i, status in enumerate(statuses):
            recording = Recording(
                file_path=f"/data/calls/test{i}.m4a",
                file_name=f"test{i}.m4a",
                file_hash=f"hashstatus{i}",
                file_size=1000,
                status=status,
            )
            async_session.add(recording)
        await async_session.commit()

        response = await async_client.get(
            "/api/v1/recordings?status=done",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == "done"

    @pytest.mark.asyncio
    async def test_list_pagination(self, async_client, auth_headers, async_session):
        """Test pagination works correctly."""
        # Create 25 recordings
        for i in range(25):
            recording = Recording(
                file_path=f"/data/calls/test{i}.m4a",
                file_name=f"test{i}.m4a",
                file_hash=f"hashpage{i}",
                file_size=1000,
                status=RecordingStatus.DISCOVERED,
            )
            async_session.add(recording)
        await async_session.commit()

        # First page
        response1 = await async_client.get(
            "/api/v1/recordings?page=1&page_size=10",
            headers=auth_headers,
        )
        data1 = response1.json()
        assert len(data1["items"]) == 10
        assert data1["total"] == 25
        assert data1["has_more"] is True

        # Second page
        response2 = await async_client.get(
            "/api/v1/recordings?page=2&page_size=10",
            headers=auth_headers,
        )
        data2 = response2.json()
        assert len(data2["items"]) == 10
        assert data2["has_more"] is True

        # Third page
        response3 = await async_client.get(
            "/api/v1/recordings?page=3&page_size=10",
            headers=auth_headers,
        )
        data3 = response3.json()
        assert len(data3["items"]) == 5
        assert data3["has_more"] is False


class TestGetRecording:
    """Tests for GET /api/v1/recordings/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_requires_auth(self, async_client):
        """Test that get endpoint requires authentication."""
        response = await async_client.get(f"/api/v1/recordings/{uuid.uuid4()}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_not_found(self, async_client, auth_headers):
        """Test getting nonexistent recording."""
        response = await async_client.get(
            f"/api/v1/recordings/{uuid.uuid4()}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_recording_details(self, async_client, auth_headers, async_session):
        """Test getting recording with full details."""
        recording = Recording(
            file_path="/data/calls/detail_test.m4a",
            file_name="detail_test.m4a",
            file_hash="detailhash123",
            file_size=2048000,
            status=RecordingStatus.DONE,
            duration_sec=120.5,
            sample_rate=44100,
            channels=2,
            codec="aac",
        )
        async_session.add(recording)
        await async_session.commit()
        await async_session.refresh(recording)

        response = await async_client.get(
            f"/api/v1/recordings/{recording.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["file_name"] == "detail_test.m4a"
        assert data["duration_sec"] == 120.5
        assert data["sample_rate"] == 44100
        assert data["status"] == "done"
        assert "processing_segments_count" in data
        assert data["processing_segments_count"] is None

    @pytest.mark.asyncio
    async def test_get_recording_returns_processing_segments_count_when_set(
        self, async_client, auth_headers, async_session
    ):
        """Test that GET recording returns processing_segments_count when in progress."""
        recording = Recording(
            file_path="/data/calls/progress_test.m4a",
            file_name="progress_test.m4a",
            file_hash="progresshash",
            file_size=1024,
            status=RecordingStatus.PROCESSING,
            processing_segments_count=12,
        )
        async_session.add(recording)
        await async_session.commit()
        await async_session.refresh(recording)

        response = await async_client.get(
            f"/api/v1/recordings/{recording.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"
        assert data["processing_segments_count"] == 12

    @pytest.mark.asyncio
    async def test_list_recordings_includes_processing_segments_count(
        self, async_client, auth_headers, async_session
    ):
        """Test that list endpoint includes processing_segments_count (null when not processing)."""
        recording = Recording(
            file_path="/data/calls/list_progress.m4a",
            file_name="list_progress.m4a",
            file_hash="listprogress",
            file_size=1024,
            status=RecordingStatus.DONE,
        )
        async_session.add(recording)
        await async_session.commit()

        response = await async_client.get(
            "/api/v1/recordings",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1
        item = next(i for i in data["items"] if i["file_name"] == "list_progress.m4a")
        assert "processing_segments_count" in item
        assert item["processing_segments_count"] is None


class TestReprocessRecording:
    """Tests for POST /api/v1/recordings/{id}/reprocess endpoint."""

    @pytest.mark.asyncio
    async def test_reprocess_requires_auth(self, async_client):
        """Test that reprocess endpoint requires authentication."""
        response = await async_client.post(f"/api/v1/recordings/{uuid.uuid4()}/reprocess")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_reprocess_not_found(self, async_client, auth_headers):
        """Test reprocessing nonexistent recording."""
        response = await async_client.post(
            f"/api/v1/recordings/{uuid.uuid4()}/reprocess",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_reprocess_queues_task(self, async_client, auth_headers, async_session):
        """Test that reprocess sets status to QUEUED (periodic enqueue_pending_recordings will enqueue)."""
        recording = Recording(
            file_path="/data/calls/reprocess_test.m4a",
            file_name="reprocess_test.m4a",
            file_hash="reprocesshash",
            file_size=1024,
            status=RecordingStatus.FAILED,
            error_message="Previous error",
        )
        async_session.add(recording)
        await async_session.commit()
        await async_session.refresh(recording)

        response = await async_client.post(
            f"/api/v1/recordings/{recording.id}/reprocess",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"

        # Verify status was reset; periodic task will enqueue
        await async_session.refresh(recording)
        assert recording.status == RecordingStatus.QUEUED
        assert recording.error_message is None

