"""Unit tests for the /ping endpoint."""

import pytest
from app.api.schemas import PingResponse

pytestmark = pytest.mark.unit

def test_ping_unit(test_client):
    """Test that ping endpoint returns pong."""
    response = test_client.get("/api/v1/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "pong"}
