import pytest
from sqlalchemy import text
from analytics.app.commands.refresh_mv import MaterializedViewRefreshCommand
from app.db.session import SyncSessionLocal

def test_refresh_caller_intelligence_mv():
    """Verify that the caller_intelligence_mv can be refreshed."""
    # This test requires the MV to exist in the database
    with SyncSessionLocal() as session:
        # First, ensure the MV exists (we'll create it in the command implementation or a migration)
        # For now, we expect the refresh command to handle it
        try:
            MaterializedViewRefreshCommand.refresh_caller_intelligence(session)
        except Exception as e:
            pytest.fail(f"Refresh failed: {e}")

def test_refresh_system_bottleneck_mv():
    """Verify that the system_bottleneck_mv can be refreshed."""
    with SyncSessionLocal() as session:
        try:
            MaterializedViewRefreshCommand.refresh_system_bottlenecks(session)
        except Exception as e:
            pytest.fail(f"Refresh failed: {e}")
