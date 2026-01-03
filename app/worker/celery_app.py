"""Celery application configuration."""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "whisper_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Worker settings - sequential processing (1 task at a time)
    worker_concurrency=settings.worker_concurrency,
    worker_prefetch_multiplier=1,

    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=settings.task_timeout_seconds,
    task_soft_time_limit=settings.task_timeout_seconds - 60,

    # Retry settings
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=settings.task_max_retries,

    # Result backend settings
    result_expires=86400,  # 24 hours

    # Broker settings
    broker_connection_retry_on_startup=True,
)

