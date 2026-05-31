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

    # Content pipeline — daily cron hour (UTC)
    RESEARCHER_CRON_HOUR: int = 6  # 6 AM UTC
    RESEARCHER_CRON_MINUTE: int = 0

    # Frontend URL (for doc links in comments)
    FRONTEND_URL: str = "http://localhost:5173"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
