from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.modules.standards.models import Standard  # add every new Mongo module's Document here

_client: AsyncIOMotorClient | None = None


async def init_mongo() -> None:
    global _client
    _client = AsyncIOMotorClient(settings.MONGO_URI)
    await init_beanie(database=_client[settings.MONGO_DB_NAME], document_models=[Standard])


async def close_mongo() -> None:
    if _client:
        _client.close()
