import pytest
import tempfile
from pathlib import Path
from sqlalchemy import select, func
from app.db.models import Recording, RecordingStatus

@pytest.mark.asyncio
async def test_ingest_bulk_behavior(async_client, auth_headers, async_session, fixtures_dir):
    """Test bulk ingest behavior with mixed new, existing, and failed files."""

    with tempfile.TemporaryDirectory(dir=fixtures_dir) as tmpdir:
        tmp_path = Path(tmpdir)

        # Create 20 files
        for i in range(20):
            (tmp_path / f"call_{i}.mp3").write_text(f"content_{i}")

        # 1. Ingest first 10
        # Clean start
        for f in tmp_path.glob("*.mp3"):
            f.unlink()

        # Batch 1: Files 0-9
        for i in range(10):
            (tmp_path / f"call_{i}.mp3").write_text(f"content_{i}")

        resp1 = await async_client.post(
            "/api/v1/ingest",
            json={"folder": str(tmp_path)},
            headers=auth_headers
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["discovered"] == 10
        assert data1["queued"] == 10
        assert data1["skipped"] == 0

        # Verify DB
        count = await async_session.scalar(select(func.count(Recording.id)))
        assert count == 10

        # Batch 2: Files 0-9 (existing) + 10-19 (new) + Duplicate content file
        for i in range(10, 20):
            (tmp_path / f"call_{i}.mp3").write_text(f"content_{i}")

        # Modify file 0 to be FAILED
        result = await async_session.execute(select(Recording).where(Recording.file_name == "call_0.mp3"))
        rec0 = result.scalar_one()
        rec0.status = RecordingStatus.FAILED
        await async_session.commit()

        # Add a duplicate file (same content as call_15.mp3)
        (tmp_path / "call_15_duplicate.mp3").write_text("content_15")

        resp2 = await async_client.post(
            "/api/v1/ingest",
            json={"folder": str(tmp_path)},
            headers=auth_headers
        )
        assert resp2.status_code == 200
        data2 = resp2.json()

        # Breakdown:
        # Files 0-9: 10 existing.
        #   Rec 0 (FAILED): 0 discovered, 1 queued.
        #   Rec 1-9 (QUEUED): 0 discovered, 0 queued, 9 skipped.
        # Files 10-19: 10 new.
        #   Rec 10-19: 10 discovered, 10 queued.
        # Duplicate file: 1 skipped (because content_15 is processed as call_15).

        # Total Expected:
        # Discovered: 10
        # Queued: 11 (1 reprocessed + 10 new)
        # Skipped: 9 (existing) + 1 (duplicate within batch) = 10

        assert data2["discovered"] == 10
        assert data2["queued"] == 11
        assert data2["skipped"] == 10

        # Verify DB count: should be 20 unique recordings (hashes)
        count = await async_session.scalar(select(func.count(Recording.id)))
        assert count == 20
