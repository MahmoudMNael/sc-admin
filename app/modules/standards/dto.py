from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StandardMetadataDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, str_strip_whitespace=True)
    standard_code: str = Field(..., min_length=1)
    version_year: str = Field(..., min_length=1)
    is_latest: bool


class StandardHierarchyDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, str_strip_whitespace=True)
    category_table_number: str = Field(..., min_length=1)
    category_title: str = Field(..., min_length=1)
    ref_number: str = Field(..., min_length=1)
    page: int = Field(..., ge=1)


class UpdateStandardMetadataRequest(BaseModel):
    """PATCH body for metadata. Identity fields (standard_code, version_year) are omitted — extra=forbid 422s them."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    is_latest: bool | None = None


class UpdateStandardHierarchyRequest(BaseModel):
    """PATCH body for hierarchy. Identity fields (category_table_number, ref_number) are omitted — extra=forbid 422s them."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    category_title: str | None = Field(None, min_length=1)
    page: int | None = Field(None, ge=1)


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
    standard_metadata: StandardMetadataDTO
    hierarchy: StandardHierarchyDTO
    activity: str = Field(..., min_length=1)
    parameters: StandardParametersDTO
    specific_requirements: str | None = None
    searchable_text: str = Field(..., min_length=1)
    # qdrant_point_id and content_hash are computed in the service — not request fields


class UpdateStandardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # identity fields + qdrant_point_id are immutable — omitted so extra="forbid" 422s any PATCH that tries
    standard_metadata: UpdateStandardMetadataRequest | None = None
    hierarchy: UpdateStandardHierarchyRequest | None = None
    activity: str | None = Field(None, min_length=1)
    parameters: StandardParametersDTO | None = None
    specific_requirements: str | None = None
    searchable_text: str | None = Field(None, min_length=1)
    # content_hash is recomputed from the merged document — not a request field


class StandardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    qdrant_point_id: str
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
    model_config = ConfigDict(extra="ignore")
    items: list[CreateStandardRequest] = Field(..., min_length=1)


class CreateManyStandardsAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["accepted"] = "accepted"
    item_count: int = Field(..., ge=1)
