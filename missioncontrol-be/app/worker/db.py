"""
Synchronous MongoDB client for Celery workers.
Motor (async) can't be used in Celery's sync context, so we use pymongo directly.
"""

from pymongo import MongoClient

from app.config import settings

_client: MongoClient | None = None


def get_sync_db():
    """Return a synchronous pymongo database handle, creating the client on first call."""
    global _client
    if _client is None:
        _client = MongoClient(settings.MONGODB_URL)
    return _client[settings.DB_NAME]
