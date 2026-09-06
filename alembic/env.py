"""Alembic env — URL from Settings.POSTGRES_DSN, metadata from SQLAlchemy Base."""

import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.core.config import settings
from app.db.postgres.base import Base
from app.modules.assets.models import Asset
from app.modules.fixtures.models import Fixture, FixtureVariant, FixtureVariantImage

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
_SQL_MODELS = (Asset, Fixture, FixtureVariant, FixtureVariantImage)


def run_migrations_offline() -> None:
    url = settings.POSTGRES_DSN
    if not url:
        raise RuntimeError("POSTGRES_DSN is not set")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    if not settings.POSTGRES_DSN:
        raise RuntimeError("POSTGRES_DSN is not set")
    connectable = create_async_engine(settings.POSTGRES_DSN)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
