"""
Centralised logging setup with daily rotation.

Every process (backend / worker / beat) writes to its own file under
`LOG_DIR`, rotated at UTC midnight. Only `LOG_BACKUP_DAYS` rotated file(s) are
kept, so nothing older than ~1 day survives on disk. Logs are also echoed to
the console so `docker compose logs <service>` still works (that stream is
size-bounded by the Docker logging driver — see docker-compose.yml).

The per-process file name comes from the `SERVICE_NAME` env var (set per
service in docker-compose) so the worker and beat don't write to the same file.
"""

import logging
import os
from logging.handlers import TimedRotatingFileHandler

from app.config import settings

_CONFIGURED = False

_FORMAT = "%(asctime)s %(levelname)s [%(processName)s %(name)s] %(message)s"


def setup_logging(service: str | None = None) -> None:
    """Configure the root logger with a daily-rotating file handler + console.

    Idempotent — safe to call from multiple entrypoints / Celery signals.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    service = service or os.getenv("SERVICE_NAME", "app")
    log_dir = settings.LOG_DIR
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        log_dir = None  # fall back to console-only if the dir isn't writable

    formatter = logging.Formatter(_FORMAT)
    handlers: list[logging.Handler] = []

    if log_dir:
        file_handler = TimedRotatingFileHandler(
            os.path.join(log_dir, f"{service}.log"),
            when="midnight",
            interval=1,
            backupCount=settings.LOG_BACKUP_DAYS,
            utc=True,
            delay=True,
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        handlers.append(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(level)
    handlers.append(console)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = handlers

    _CONFIGURED = True
    logging.getLogger(__name__).info(
        "Logging configured for '%s' (level=%s, dir=%s, daily rotation, keep=%s)",
        service, settings.LOG_LEVEL, log_dir, settings.LOG_BACKUP_DAYS,
    )
