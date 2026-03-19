import os

def test_alembic_initialized():
    """Verify that Alembic is initialized for the analytics service."""
    # Check for alembic.ini in the analytics root
    assert os.path.exists("analytics/alembic.ini")
    
    # Check for the migrations directory
    assert os.path.isdir("analytics/app/db/migrations")
    assert os.path.exists("analytics/app/db/migrations/env.py")
    assert os.path.exists("analytics/app/db/migrations/script.py.mako")
