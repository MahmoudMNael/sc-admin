from datetime import datetime

from beanie import Document
from pydantic import BaseModel
from pymongo import ASCENDING, IndexModel


class StandardMetadata(BaseModel):
    standard_code: str
    version_year: str
    is_latest: bool


class StandardHierarchy(BaseModel):
    category_table_number: str
    category_title: str
    ref_number: str
    page: int


class StandardParameters(BaseModel):
    em_r_lx: float | None = None
    em_u_lx: float | None = None
    uo: float | None = None
    ra: float | None = None
    ugr_rugl: float | None = None
    ez_lx: float | None = None
    em_wall_lx: float | None = None
    em_ceiling_lx: float | None = None


class Standard(Document):
    id: str  # domain-provided natural key — also becomes Mongo's _id (see Section 10)
    qdrant_point_id: int
    standard_metadata: StandardMetadata
    hierarchy: StandardHierarchy
    activity: str
    parameters: StandardParameters
    specific_requirements: str | None = None
    searchable_text: str
    content_hash: str  # computed — never taken from the request
    created_at: datetime
    updated_at: datetime

    class Settings:
        name = "standards"
        indexes = [
            IndexModel([("qdrant_point_id", ASCENDING)], unique=True),
            IndexModel([("standard_metadata.standard_code", ASCENDING)]),
            IndexModel([("standard_metadata.version_year", ASCENDING)]),
            IndexModel([("standard_metadata.is_latest", ASCENDING)]),
            IndexModel([("hierarchy.category_table_number", ASCENDING)]),
            IndexModel([("hierarchy.ref_number", ASCENDING)]),
            IndexModel([("activity", ASCENDING)]),
        ]
