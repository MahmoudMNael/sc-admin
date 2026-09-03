from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StandardMetadataDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    standard_code: str = Field(..., min_length=1)
    version_year: str = Field(..., min_length=1)
    is_latest: bool


class StandardHierarchyDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    category_table_number: str = Field(..., min_length=1)
    category_title: str = Field(..., min_length=1)
    ref_number: str = Field(..., min_length=1)
    page: int = Field(..., ge=1)


class StandardParametersDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    em_r_lx: float | None = Field(None, ge=0)
    em_u_lx: float | None = Field(None, ge=0)
    uo: float | None = Field(None, ge=0, le=1)
    ra: float | None = Field(None, ge=0, le=100)
    ugr_rugl: float | None = Field(None, ge=0)
    ez_lx: float | None = Field(None, ge=0)
    em_wall_lx: float | None = Field(None, ge=0)
    em_ceiling_lx: float | None = Field(None, ge=0)


class CreateStandardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)

    id: str = Field(
        ...,
        min_length=1,
        alias="_id",
        description="Deterministic natural key, e.g. 'en12464_1_v2019_6_1_1'",
    )
    qdrant_point_id: int  # stored as sent; unique; not computed
    standard_metadata: StandardMetadataDTO
    hierarchy: StandardHierarchyDTO
    activity: str = Field(..., min_length=1)
    parameters: StandardParametersDTO
    specific_requirements: str | None = None
    searchable_text: str = Field(..., min_length=1)
    # content_hash is computed in the service — not a request field


class UpdateStandardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # qdrant_point_id is immutable after create — omitting it here makes extra="forbid" 422 any PATCH that tries
    standard_metadata: StandardMetadataDTO | None = None
    hierarchy: StandardHierarchyDTO | None = None
    activity: str | None = Field(None, min_length=1)
    parameters: StandardParametersDTO | None = None
    specific_requirements: str | None = None
    searchable_text: str | None = Field(None, min_length=1)
    # content_hash is recomputed from the merged document — not a request field


class StandardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    qdrant_point_id: int
    standard_metadata: StandardMetadataDTO
    hierarchy: StandardHierarchyDTO
    activity: str
    parameters: StandardParametersDTO
    specific_requirements: str | None
    searchable_text: str
    content_hash: str
    created_at: datetime
    updated_at: datetime


class CreateManyStandardsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[CreateStandardRequest] = Field(..., min_length=1)


class CreateManyStandardsAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["accepted"] = "accepted"
    item_count: int = Field(..., ge=1)
