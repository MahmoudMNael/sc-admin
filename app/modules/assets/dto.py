from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    relative_path: str
    original_filename: str
    mime_type: str
    size_bytes: int = Field(..., ge=0)
    created_at: datetime
