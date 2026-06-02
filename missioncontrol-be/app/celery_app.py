from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging as _setup_logging_signal

from app.config import settings


@_setup_logging_signal.connect
def _configure_celery_logging(**_kwargs):
    """Use our daily-rotating logging instead of Celery's default config.

    Connecting to this signal tells Celery NOT to configure logging itself, so
    the handlers we install (file rotation + console) are the only ones used by
    both the worker and beat processes.
    """
    from app.logging_config import setup_logging
    setup_logging()


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
        "daily-cron": {
            "task": "daily_cron",
            "schedule": crontab(
                hour=settings.DAILY_CRON_HOUR,
                minute=settings.DAILY_CRON_MINUTE,
            ),
        },
    },
)

# Auto-discover tasks in app.worker package
celery.autodiscover_tasks(["app.worker"])
