import pytest
from httpx import AsyncClient

# Mark all tests in this file as async
pytestmark = pytest.mark.asyncio

async def test_queue_status_unauthenticated(async_client: AsyncClient):
    """Test that queue status is NOT accessible without authentication (fixed state)."""
    # The routes are usually prefixed with /api/v1
    response = await async_client.get("/api/v1/queue/status")
    # AFTER FIX: This should fail (401 Unauthorized)
    assert response.status_code == 401

async def test_queue_status_authenticated(async_client: AsyncClient, test_settings):
    """Test that queue status is accessible with authentication."""
    headers = {"Authorization": f"Bearer {test_settings.api_token}"}
    response = await async_client.get("/api/v1/queue/status", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "queued" in data
