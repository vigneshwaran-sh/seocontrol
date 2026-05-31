from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery = Celery(
    "missioncontrol",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_hijack_root_logger=False,
    beat_schedule={
        "poll-agent-tasks": {
            "task": "poll_agent_tasks",
            "schedule": settings.AGENT_POLL_INTERVAL_SECONDS,
        },
        "daily-content-researcher": {
            "task": "run_content_researcher_all",
            "schedule": crontab(
                hour=settings.RESEARCHER_CRON_HOUR,
                minute=settings.RESEARCHER_CRON_MINUTE,
            ),
        },
    },
)

# Auto-discover tasks in app.worker package
celery.autodiscover_tasks(["app.worker"])
