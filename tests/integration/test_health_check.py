"""Integration tests for the health check endpoint."""

import pytest
from pathlib import Path
from unittest.mock import patch
from app.config import get_settings
from app.main import app
from tests.conftest import get_test_settings

pytestmark = pytest.mark.integration

@pytest.mark.asyncio
async def test_health_check_success(async_client, tmp_path):
    """Test health check returns ok when storage is accessible."""
    # Override settings to use tmp_path as calls_dir
    new_settings = get_test_settings()
    new_settings.calls_dir = str(tmp_path)
    app.dependency_overrides[get_settings] = lambda: new_settings

    # Mock Redis to be healthy (Celery inspect)
    with patch("app.worker.celery_app.celery_app.control.inspect") as mock_inspect:
        mock_inspect.return_value.active.return_value = {"worker1": []}

        response = await async_client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "ok"
        assert data["redis"] == "ok"
        assert data["storage"] == "ok"

        # Verify .health_check file was cleaned up
        assert not any(f.name.startswith(".health_check_") for f in tmp_path.iterdir())

@pytest.mark.asyncio
async def test_health_check_storage_failure(async_client):
    """Test health check returns error/degraded when storage is missing."""
    # Override settings to use a non-existent path
    new_settings = get_test_settings()
    new_settings.calls_dir = "/non/existent/path/12345"
    app.dependency_overrides[get_settings] = lambda: new_settings

    with patch("app.worker.celery_app.celery_app.control.inspect") as mock_inspect:
        mock_inspect.return_value.active.return_value = {"worker1": []}

        response = await async_client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["storage"] == "error"

@pytest.mark.asyncio
async def test_health_check_storage_readonly(async_client, tmp_path):
    """Test health check returns read_only when storage is not writable."""
    new_settings = get_test_settings()
    new_settings.calls_dir = str(tmp_path)
    app.dependency_overrides[get_settings] = lambda: new_settings

    # Mock pathlib.Path.touch to simulate PermissionError
    with patch("pathlib.Path.touch", side_effect=PermissionError("Mock permission denied")):
        with patch("app.worker.celery_app.celery_app.control.inspect") as mock_inspect:
            mock_inspect.return_value.active.return_value = {"worker1": []}

            response = await async_client.get("/api/v1/health")

            assert response.status_code == 200
            data = response.json()
            assert data["storage"] == "read_only"
            assert data["status"] == "degraded"
