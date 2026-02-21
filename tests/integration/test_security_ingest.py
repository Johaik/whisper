
import os
import tempfile
import pytest
from pathlib import Path
from httpx import AsyncClient
from app.config import Settings

@pytest.mark.asyncio
async def test_ingest_path_traversal_reproduction(async_client: AsyncClient):
    """
    Test to reproduce the path traversal vulnerability.
    We create a temporary directory outside the allowed 'calls_dir'
    and attempt to ingest it.
    If the vulnerability exists, this will succeed (status 200).
    Now that it's fixed, it should fail (status 403).
    """
    # Create a temporary directory outside of the configured calls_dir
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir).resolve()

        # Create a dummy audio file in it
        dummy_file = temp_path / "test.mp3"
        dummy_file.write_bytes(b"dummy audio content")

        # Attempt to ingest the external directory
        response = await async_client.post(
            "/api/v1/ingest",
            json={"folder": str(temp_path), "force_reprocess": True},
            headers={"Authorization": "Bearer test-token"}
        )

        assert response.status_code == 403, f"Fix failed: External folder was not blocked. Status: {response.status_code}"
        assert "Access denied" in response.json()["detail"]


@pytest.mark.asyncio
async def test_ingest_valid_path(async_client: AsyncClient, test_settings: Settings):
    """
    Test that ingesting a valid subdirectory works.
    """
    calls_dir = Path(test_settings.calls_dir)

    # Ensure calls_dir exists
    calls_dir.mkdir(parents=True, exist_ok=True)

    # Create a subdirectory inside calls_dir
    sub_dir = calls_dir / "valid_subdir"
    sub_dir.mkdir(exist_ok=True)

    try:
        # Create a dummy audio file in it
        dummy_file = sub_dir / "valid.mp3"
        dummy_file.write_bytes(b"dummy audio content")

        # Attempt to ingest the valid directory
        response = await async_client.post(
            "/api/v1/ingest",
            json={"folder": str(sub_dir), "force_reprocess": True},
            headers={"Authorization": "Bearer test-token"}
        )

        # It should succeed (200)
        assert response.status_code == 200, f"Valid folder was blocked: {response.text}"
        data = response.json()
        assert data["discovered"] >= 1

    finally:
        # Cleanup
        if dummy_file.exists():
            dummy_file.unlink()
        if sub_dir.exists():
            sub_dir.rmdir()
