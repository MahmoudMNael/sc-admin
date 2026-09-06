from uuid import UUID

from app.shared.repository.sql_repository import SQLRepository

from .models import Asset


class AssetRepository(SQLRepository[Asset, UUID]):
    model = Asset
