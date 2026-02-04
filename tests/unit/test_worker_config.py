"""Unit tests for worker-related config and Celery app (no DB/Redis)."""

import pytest


@pytest.mark.unit
class TestWorkerConfig:
    """Test config used by worker: optional timeout, stuck threshold, heartbeat."""

    def test_task_timeout_optional_none(self) -> None:
        """task_timeout_seconds can be None (no Celery time limit)."""
        from app.config import Settings

        s = Settings(
            database_url="sqlite:///",
            database_url_sync="sqlite:///",
            redis_url="redis://localhost/0",
            task_timeout_seconds=None,
        )
        assert s.task_timeout_seconds is None

    def test_task_timeout_zero_becomes_none(self) -> None:
        """task_timeout_seconds=0 is coerced to None (no limit)."""
        from app.config import Settings

        s = Settings(
            database_url="sqlite:///",
            database_url_sync="sqlite:///",
            redis_url="redis://localhost/0",
            task_timeout_seconds=0,
        )
        assert s.task_timeout_seconds is None

    def test_stuck_and_heartbeat_defaults(self) -> None:
        """stuck_processing_threshold_sec and heartbeat_interval_sec have defaults."""
        from app.config import Settings

        s = Settings(
            database_url="sqlite:///",
            database_url_sync="sqlite:///",
            redis_url="redis://localhost/0",
        )
        assert s.stuck_processing_threshold_sec >= 900
        assert s.heartbeat_interval_sec >= 60


@pytest.mark.unit
class TestCeleryAppLoads:
    """Test that Celery app loads and time limit logic is conditional."""

    def test_celery_app_has_expected_conf_keys(self) -> None:
        """Celery app has task_time_limit and task_soft_time_limit or neither (no limit)."""
        try:
            from app.worker.celery_app import celery_app
        except (ModuleNotFoundError, ImportError):
            pytest.skip("worker/celery imports need DB driver (e.g. psycopg2)")
        limit = celery_app.conf.get("task_time_limit")
        soft = celery_app.conf.get("task_soft_time_limit")
        # When task_timeout_seconds is None/unset: both None. When set: both set.
        if limit is not None:
            assert soft is not None
            assert soft == limit - 60
        else:
            assert soft is None
