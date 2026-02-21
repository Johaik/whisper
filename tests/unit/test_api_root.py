"""Unit tests for the root endpoint."""

import pytest
from app import __version__

pytestmark = pytest.mark.unit

def test_root_endpoint(test_client):
    """Test that the root endpoint returns API info."""
    response = test_client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "name": "Hebrew Transcription Pipeline",
        "version": __version__,
        "docs": "/docs",
    }
