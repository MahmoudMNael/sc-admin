from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.postgres.session import get_postgres_session
from app.storage.base import AbstractFileStorage
from app.storage.local import LocalFileStorage

from .repository import AssetRepository
from .service import AssetService


def get_asset_repository(
    session: Annotated[AsyncSession, Depends(get_postgres_session)],
) -> AssetRepository:
    return AssetRepository(session)


AssetRepositoryDep = Annotated[AssetRepository, Depends(get_asset_repository)]


def get_file_storage() -> AbstractFileStorage:
    return LocalFileStorage(settings.LOCAL_STORAGE_PATH)


def get_asset_service(
    repo: AssetRepositoryDep,
    storage: Annotated[AbstractFileStorage, Depends(get_file_storage)],
) -> AssetService:
    return AssetService(repo, storage)


AssetServiceDep = Annotated[AssetService, Depends(get_asset_service)]
