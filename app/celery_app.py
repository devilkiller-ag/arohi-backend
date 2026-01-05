"""Celery application configuration for background tasks."""

import sys
from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "arohi",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.followup_tasks"],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task execution settings
    task_acks_late=True,  # Acknowledge after task completes (reliability)
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # One task at a time per worker

    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour

    # Windows compatibility: use 'solo' pool instead of 'prefork'
    # In production (Linux), prefork is used automatically
    worker_pool="solo" if sys.platform == "win32" else "prefork",

    # Broker connection retry settings (Celery 6.0 compatibility)
    broker_connection_retry_on_startup=True,

    # Beat scheduler for periodic tasks
    beat_schedule={
        # Check for users needing follow-up every hour
        "check-followups-hourly": {
            "task": "app.tasks.followup_tasks.check_and_send_followups",
            "schedule": crontab(minute=0),  # Every hour at :00
        },
        # Process scheduled reminders every minute
        "process-scheduled-reminders": {
            "task": "app.tasks.followup_tasks.process_scheduled_reminders",
            "schedule": crontab(),  # Every minute
        },
    },
)
