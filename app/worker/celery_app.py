"""Celery application configuration."""

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "whisper_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

# Celery configuration
_conf: dict = {
    # Task settings
    "task_serializer": "json",
    "accept_content": ["json"],
    "result_serializer": "json",
    "timezone": "UTC",
    "enable_utc": True,
    # Worker settings - sequential processing (1 task at a time)
    "worker_concurrency": settings.worker_concurrency,
    "worker_prefetch_multiplier": 1,
    # Task execution settings
    "task_acks_late": True,
    "task_reject_on_worker_lost": True,
    # Retry settings
    "task_default_retry_delay": 60,
    "task_max_retries": settings.task_max_retries,
    # Result backend settings
    "result_expires": 86400,
    # Broker settings
    "broker_connection_retry_on_startup": True,
    # Events for Flower monitoring
    "worker_send_task_events": True,
    "task_send_sent_event": True,
}
# Only set time limits when task_timeout_seconds is set; otherwise no limit (stuck = no heartbeat)
if settings.task_timeout_seconds and settings.task_timeout_seconds > 0:
    _conf["task_time_limit"] = settings.task_timeout_seconds
    _conf["task_soft_time_limit"] = settings.task_timeout_seconds - 60
celery_app.conf.update(_conf)

# Periodic cleanup of stuck recordings (run worker with --beat or run celery beat)
celery_app.conf.beat_schedule = {
    "cleanup-stuck-recordings": {
        "task": "cleanup_stuck_recordings",
        "schedule": crontab(minute="*/15"),  # every 15 minutes
    },
}

