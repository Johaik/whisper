"""Integration tests for API authentication."""

import pytest


pytestmark = pytest.mark.integration


class TestAuthentication:
    """Tests for API authentication."""

    @pytest.mark.asyncio
    async def test_health_no_auth_required(self, async_client):
        """Test that /health endpoint doesn't require auth."""
        response = await async_client.get("/api/v1/health")
        # May return degraded if DB not available, but shouldn't be 401
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_missing_auth_header(self, async_client):
        """Test request without Authorization header."""
        response = await async_client.get("/api/v1/recordings")
        assert response.status_code == 401
        assert "Missing" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_invalid_token(self, async_client):
        """Test request with invalid token."""
        response = await async_client.get(
            "/api/v1/recordings",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401
        assert "Invalid" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_valid_token(self, async_client, auth_headers):
        """Test request with valid token."""
        response = await async_client.get(
            "/api/v1/recordings",
            headers=auth_headers,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_malformed_auth_header(self, async_client):
        """Test request with malformed Authorization header."""
        # Missing "Bearer" prefix
        response = await async_client.get(
            "/api/v1/recordings",
            headers={"Authorization": "test-token"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_bearer_token(self, async_client):
        """Test request with empty bearer token."""
        response = await async_client.get(
            "/api/v1/recordings",
            headers={"Authorization": "Bearer "},
        )
        assert response.status_code == 401


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_status(self, async_client):
        """Test health endpoint returns proper structure."""
        response = await async_client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data
        assert "database" in data
        assert "redis" in data

    @pytest.mark.asyncio
    async def test_health_includes_version(self, async_client):
        """Test health endpoint includes version."""
        response = await async_client.get("/api/v1/health")
        data = response.json()
        assert data["version"] == "1.0.0"

