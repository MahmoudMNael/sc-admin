from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.assets.dto import AssetResponse
from app.modules.fixtures.models import ElectricalProtection, FixtureApplication


def _unique(items: list) -> list:
    if len(items) != len(set(items)):
        raise ValueError("values must be unique")
    return items


class CreateFixtureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    manufacturer_name: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    is_main_solution: bool = False
    applications: list[FixtureApplication] = Field(..., min_length=1, max_length=2)

    @field_validator("applications")
    @classmethod
    def unique_applications(cls, value: list[FixtureApplication]) -> list[FixtureApplication]:
        return _unique(value)


class UpdateFixtureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    manufacturer_name: str | None = Field(None, min_length=1)
    name: str | None = Field(None, min_length=1)
    is_main_solution: bool | None = None
    applications: list[FixtureApplication] | None = Field(None, min_length=1, max_length=2)

    @field_validator("applications")
    @classmethod
    def unique_applications(cls, value: list[FixtureApplication] | None) -> list[FixtureApplication] | None:
        return None if value is None else _unique(value)


class CreateVariantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., min_length=1)
    power: int = Field(..., ge=0)
    chip: str = Field(..., min_length=1)
    driver: str = Field(..., min_length=1)
    power_factor: Decimal = Field(..., ge=0, le=1)
    cri: Decimal = Field(..., ge=0)
    efficacy: int = Field(..., ge=0)
    mechanical_protections: list[str] = Field(default_factory=list)
    electrical_protections: list[ElectricalProtection] = Field(default_factory=list)
    dimension_length: Decimal | None = Field(None, ge=0)
    dimension_width: Decimal | None = Field(None, ge=0)
    dimension_depth: Decimal | None = Field(None, ge=0)
    dimension_radius: Decimal | None = Field(None, ge=0)
    model_3d_file_id: UUID | None = None
    ies_file_id: UUID

    @field_validator("mechanical_protections")
    @classmethod
    def unique_mechanical(cls, value: list[str]) -> list[str]:
        return _unique(value)

    @field_validator("electrical_protections")
    @classmethod
    def unique_electrical(cls, value: list[ElectricalProtection]) -> list[ElectricalProtection]:
        return _unique(value)


class UpdateVariantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(None, min_length=1)
    power: int | None = Field(None, ge=0)
    chip: str | None = Field(None, min_length=1)
    driver: str | None = Field(None, min_length=1)
    power_factor: Decimal | None = Field(None, ge=0, le=1)
    cri: Decimal | None = Field(None, ge=0)
    efficacy: int | None = Field(None, ge=0)
    mechanical_protections: list[str] | None = None
    electrical_protections: list[ElectricalProtection] | None = None
    dimension_length: Decimal | None = Field(None, ge=0)
    dimension_width: Decimal | None = Field(None, ge=0)
    dimension_depth: Decimal | None = Field(None, ge=0)
    dimension_radius: Decimal | None = Field(None, ge=0)
    model_3d_file_id: UUID | None = None
    ies_file_id: UUID

    @field_validator("mechanical_protections")
    @classmethod
    def unique_mechanical(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _unique(value)

    @field_validator("electrical_protections")
    @classmethod
    def unique_electrical(cls, value: list[ElectricalProtection] | None) -> list[ElectricalProtection] | None:
        return None if value is None else _unique(value)


class CreateVariantImageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_file_id: UUID


class VariantImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    variant_id: UUID
    image_file_id: UUID
    image_file: AssetResponse


class VariantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fixture_id: UUID
    name: str
    power: int
    chip: str
    driver: str
    power_factor: Decimal
    cri: Decimal
    efficacy: int
    mechanical_protections: list[str]
    electrical_protections: list[str]
    dimension_length: Decimal | None
    dimension_width: Decimal | None
    dimension_depth: Decimal | None
    dimension_radius: Decimal | None
    model_3d_file_id: UUID | None
    model_3d_file: AssetResponse | None
    ies_file_id: UUID
    ies_file: AssetResponse
    images: list[VariantImageResponse]
    created_at: datetime
    updated_at: datetime


class FixtureSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    manufacturer_name: str
    name: str
    is_main_solution: bool
    applications: list[str]
    created_at: datetime
    updated_at: datetime


class FixtureResponse(FixtureSummaryResponse):
    variants: list[VariantResponse]


class VariantDetailResponse(VariantResponse):
    fixture: FixtureSummaryResponse
