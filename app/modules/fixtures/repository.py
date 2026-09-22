from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.shared.repository.sql_repository import SQLRepository

from .models import Fixture, FixtureVariant, FixtureVariantImage

VARIANT_LOAD_OPTIONS = (
    selectinload(FixtureVariant.model_3d_file),
    selectinload(FixtureVariant.images).selectinload(FixtureVariantImage.image_file),
    selectinload(FixtureVariant.ies_file),
    selectinload(FixtureVariant.fixture)
)


class FixtureRepository(SQLRepository[Fixture, UUID]):
    model = Fixture

    # def _options(self):
    #     return (selectinload(Fixture.ies_file))

    async def get_with_variants(self, id: UUID) -> Fixture | None:
        stmt = (
            select(Fixture)
            .options(
                *self._options(),
                selectinload(Fixture.variants).options(*VARIANT_LOAD_OPTIONS),
            )
            .where(Fixture.id == id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class FixtureVariantRepository(SQLRepository[FixtureVariant, UUID]):
    model = FixtureVariant

    def _options(self):
        return VARIANT_LOAD_OPTIONS

    async def get_with_fixture(self, id: UUID) -> FixtureVariant | None:
        stmt = (
            select(FixtureVariant)
            .options(
                *self._options(),
                selectinload(FixtureVariant.fixture),
            )
            .where(FixtureVariant.id == id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class FixtureVariantImageRepository(SQLRepository[FixtureVariantImage, UUID]):
    model = FixtureVariantImage

    def _options(self):
        return (selectinload(FixtureVariantImage.image_file),)
