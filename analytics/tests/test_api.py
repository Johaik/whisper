import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_get_caller_analytics():
    """Verify the /analytics/caller/{phone} endpoint."""
    response = client.get("/api/v1/analytics/caller/123456789", headers={"Authorization": "Bearer super-secure-dev-token-999"})
    # We expect 404 or 200 depending on DB state, but for now we expect 200 if we mock it
    # But since we haven't implemented the route, we expect 404
    assert response.status_code == 200

def test_get_system_bottlenecks():
    """Verify the /analytics/bottlenecks endpoint."""
    response = client.get("/api/v1/analytics/bottlenecks", headers={"Authorization": "Bearer super-secure-dev-token-999"})
    assert response.status_code == 200

def test_semantic_search():
    """Verify the /analytics/search endpoint."""
    payload = {"query_text": "billing issue"}
    response = client.post("/api/v1/analytics/search", json=payload, headers={"Authorization": "Bearer super-secure-dev-token-999"})
    assert response.status_code == 200
