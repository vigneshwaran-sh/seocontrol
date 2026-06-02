from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGODB_URL: str = "mongodb://localhost:27017"
    DB_NAME: str = "missioncontrol"
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]
    SECRET_KEY: str = "changeme"
    ACCESS_TOKEN_EXPIRE_HOURS: int = 24

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    AGENT_POLL_INTERVAL_SECONDS: int = 30

    # Daily cron (UTC). Default 22:30 UTC == 04:00 IST (India, UTC+5:30) — the
    # daily_cron task seeds a fresh topic-research task for the Content Researcher.
    DAILY_CRON_HOUR: int = 22
    DAILY_CRON_MINUTE: int = 30

    # Frontend URL (for doc links in comments)
    FRONTEND_URL: str = "http://localhost:5173"

    # Logging — daily rotation, retain ≤ 1 day.
    LOG_DIR: str = "logs"           # directory for rotating process logs
    LOG_LEVEL: str = "INFO"
    LOG_BACKUP_DAYS: int = 1        # rotated files kept (1 = today + yesterday only)
    # Agent (LLM) call logs in MongoDB auto-expire after this many seconds.
    LLM_LOG_TTL_SECONDS: int = 86400  # 1 day

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
