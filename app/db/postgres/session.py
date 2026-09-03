from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        if not settings.POSTGRES_DSN:
            raise RuntimeError("POSTGRES_DSN is not set")
        engine = create_async_engine(settings.POSTGRES_DSN)
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


async def get_postgres_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session
