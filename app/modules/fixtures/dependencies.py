from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.session import get_postgres_session
from app.modules.assets.dependencies import get_asset_repository
from app.modules.assets.repository import AssetRepository

from .repository import (
    FixtureRepository,
    FixtureVariantImageRepository,
    FixtureVariantRepository,
)
from .service import FixtureService


def get_fixture_repository(
    session: Annotated[AsyncSession, Depends(get_postgres_session)],
) -> FixtureRepository:
    return FixtureRepository(session)


def get_fixture_variant_repository(
    session: Annotated[AsyncSession, Depends(get_postgres_session)],
) -> FixtureVariantRepository:
    return FixtureVariantRepository(session)


def get_fixture_variant_image_repository(
    session: Annotated[AsyncSession, Depends(get_postgres_session)],
) -> FixtureVariantImageRepository:
    return FixtureVariantImageRepository(session)


def get_fixture_service(
    fixtures: Annotated[FixtureRepository, Depends(get_fixture_repository)],
    variants: Annotated[FixtureVariantRepository, Depends(get_fixture_variant_repository)],
    images: Annotated[FixtureVariantImageRepository, Depends(get_fixture_variant_image_repository)],
    assets: Annotated[AssetRepository, Depends(get_asset_repository)],
) -> FixtureService:
    return FixtureService(fixtures, variants, images, assets)


FixtureServiceDep = Annotated[FixtureService, Depends(get_fixture_service)]
