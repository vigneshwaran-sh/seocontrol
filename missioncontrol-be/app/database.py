from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings

client: AsyncIOMotorClient | None = None


async def connect_db() -> None:
    global client
    client = AsyncIOMotorClient(settings.MONGODB_URL)


async def close_db() -> None:
    global client
    if client is not None:
        client.close()
        client = None


def get_db():
    if client is None:
        raise RuntimeError("Database client is not initialised. Call connect_db() first.")
    return client[settings.DB_NAME]
