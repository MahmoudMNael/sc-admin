# FastAPI Modular CRUD Architecture — Repository Pattern (Dual ORM + Local File Storage)

**Standards is the first implemented module.** Every future module (Postgres or Mongo, with or without file storage) should mirror its shape exactly — see Section 16 for the checklist.

## 1. Goals & Constraints

- **Layers**: `Controller → Service → Repository → (Postgres | MongoDB | Local FS)`. Services hold business logic; controllers stay thin (validation + delegation); repositories only know how to talk to a single data source.
- **Two ORMs, one pattern**: SQLAlchemy 2.x (async) for Postgres, Beanie (async, built on Motor + Pydantic) for MongoDB. Both are hidden behind the same repository abstraction so services never import `sqlalchemy` or `beanie` directly.
- **File uploads are a repository too**: local filesystem storage is abstracted the same way DB access is, so it can be swapped for S3/GCS later without touching services. (No module needs this yet — the abstraction is ready for when one does.)
- **Feature-based modules**: every domain concept lives in its own folder with `controller.py`, `service.py`, `repository.py`, `models.py` (ORM/ODM entities), `dto.py` (Pydantic schemas), `dependencies.py` (DI wiring).
- **Strict validation everywhere**: every request/response body is a distinct Pydantic model with `extra="forbid"`, explicit `Field` constraints, and shows up correctly in Swagger via `response_model`.
- **DI**: native FastAPI `Depends` + `Annotated` aliases — no extra DI framework needed for a CRUD app.
- **Idempotent writes**: modules built around externally-sourced, deterministic data (like Standards) treat `create` as safe to retry; bulk create is accepted asynchronously — see Section 10.
- **Tests never touch the real world**: no Mongo, no Postgres, no disk. Controllers and services are exercised with in-memory fakes — see Section 15.
- **Auth deliberately excluded**: noted only as a placeholder seam (`get_current_user` dependency) to wire in later without restructuring.

---

## 2. Package List

```bash
# Core
fastapi
uvicorn[standard]
pydantic>=2
pydantic-settings

# Postgres (SQLAlchemy async) — infra ready, no module uses it yet
sqlalchemy>=2
asyncpg
alembic

# MongoDB
beanie                  # includes motor & pydantic integration
motor

# File uploads — infra ready, no module uses it yet
python-multipart
aiofiles

# Dev / quality
pytest
pytest-asyncio
httpx
ruff
mypy
```

```bash
pip install fastapi "uvicorn[standard]" pydantic pydantic-settings \
  sqlalchemy asyncpg alembic beanie motor \
  python-multipart aiofiles \
  pytest pytest-asyncio httpx ruff mypy
```

---

## 3. Folder Structure

```
app/
├── main.py                      # app factory, router registration, lifespan
├── core/
│   ├── config.py                 # pydantic-settings Settings
│   ├── exceptions.py             # domain exceptions + handlers
│   └── logging.py
├── db/
│   ├── postgres/
│   │   ├── base.py                # SQLAlchemy declarative Base (unused until first SQL module)
│   │   └── session.py             # async engine + session dependency
│   └── mongo/
│       └── client.py              # Motor client + init_beanie()
├── storage/
│   ├── base.py                    # AbstractFileStorage interface (unused until first upload module)
│   └── local.py                   # LocalFileStorage implementation
├── shared/
│   ├── dto/
│   │   ├── error.py                # ErrorResponse schema
│   │   └── pagination.py           # generic Page[T] wrapper (not used yet — see Roadmap)
│   ├── specification/
│   │   ├── base.py                 # Specification[Model] — ORM-agnostic composable criteria
│   │   ├── fields.py               # FieldEquals
│   │   ├── keyword.py              # KeywordSpecification — multi-field keyword search
│   │   └── match_all.py            # MatchAllSpecification — identity element for dynamic filters
│   ├── utils/
│   │   └── qdrant.py               # UUID v5 qdrant point id from identity fields
│   └── repository/
│       ├── base.py                 # AbstractRepository[Entity, ID]
│       ├── sql_repository.py       # generic SQLAlchemy CRUD base
│       └── mongo_repository.py     # generic Beanie CRUD base
├── modules/
│   └── standards/                  # ← first real module, mirror this shape for every new one
│       ├── controller.py
│       ├── service.py
│       ├── repository.py
│       ├── models.py
│       ├── dto.py
│       └── dependencies.py
└── tests/                       # in-memory only — never a real DB or filesystem (Section 15)
    ├── conftest.py
    └── modules/
        └── standards/...
```

---

## 4. Layer Responsibilities

| Layer            | Knows about                                                                                   | Must NOT know about                                                        |
| ---------------- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| **Controller**   | FastAPI routing, DTOs, HTTP status codes, the Service                                         | ORM/ODM models, sessions, business rules                                   |
| **Service**      | Business logic, orchestration across 1+ repositories, DTO ↔ entity mapping, idempotency rules | HTTP concerns (status codes, `Request`/`Response`), SQL/Mongo query syntax |
| **Repository**   | One data source (a Postgres table, a Mongo collection, or local disk) and its query mechanics | Business rules, DTOs                                                       |
| **Entity/Model** | Table/document schema                                                                         | Nothing outward-facing — never returned directly from a controller         |
| **DTO**          | Pydantic request/response contracts, field-level validation                                   | Persistence details                                                        |

**Rule of thumb**: DTOs cross the controller boundary, entities cross the repository boundary, and the service is the only place allowed to see both.

---

## 5. Shared Repository Infrastructure

Written once, extended by every module's `repository.py`. A concrete module repo just sets `model = <YourModel>` — see `StandardRepository` in Section 9.

### 5a. Abstract base

```python
# shared/repository/base.py
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, Sequence
from app.shared.specification.base import Specification

EntityT = TypeVar("EntityT")
IdT = TypeVar("IdT")

class AbstractRepository(ABC, Generic[EntityT, IdT]):
    @abstractmethod
    async def create(self, entity: EntityT) -> EntityT: ...

    @abstractmethod
    async def create_many(self, entities: Sequence[EntityT]) -> Sequence[EntityT]: ...

    @abstractmethod
    async def get_by_id(self, id: IdT) -> Optional[EntityT]: ...

    @abstractmethod
    async def get_many_by_ids(self, ids: Sequence[IdT]) -> Sequence[EntityT]: ...

    @abstractmethod
    async def list(self, skip: int = 0, limit: int = 100) -> Sequence[EntityT]: ...

    @abstractmethod
    async def find(self, spec: Specification, skip: int = 0, limit: int = 100) -> Sequence[EntityT]:
        """Return entities matching an arbitrary Specification. See Section 6."""

    @abstractmethod
    async def update(self, id: IdT, data: dict) -> Optional[EntityT]: ...

    @abstractmethod
    async def delete(self, id: IdT) -> bool: ...
```

### 5b. SQLAlchemy (Postgres) generic base

Assumes every SQLAlchemy model exposes its primary key as `.id` (as `Product`, `Order`, etc. would).

```python
# shared/repository/sql_repository.py
from typing import Generic, TypeVar, Type, Optional, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.repository.base import AbstractRepository
from app.shared.specification.base import Specification

ModelT = TypeVar("ModelT")

class SQLRepository(AbstractRepository[ModelT, int], Generic[ModelT]):
    model: Type[ModelT]

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    async def create_many(self, entities: Sequence[ModelT]) -> Sequence[ModelT]:
        if not entities:
            return []
        self.session.add_all(entities)
        await self.session.commit()
        for entity in entities:
            await self.session.refresh(entity)
        return entities

    async def get_by_id(self, id: int) -> Optional[ModelT]:
        return await self.session.get(self.model, id)

    async def get_many_by_ids(self, ids: Sequence[int]) -> Sequence[ModelT]:
        if not ids:
            return []
        result = await self.session.execute(select(self.model).where(self.model.id.in_(ids)))
        return result.scalars().all()

    async def list(self, skip: int = 0, limit: int = 100) -> Sequence[ModelT]:
        result = await self.session.execute(select(self.model).offset(skip).limit(limit))
        return result.scalars().all()

    async def find(self, spec: Specification, skip: int = 0, limit: int = 100) -> Sequence[ModelT]:
        stmt = select(self.model).where(spec.to_sql(self.model)).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update(self, id: int, data: dict) -> Optional[ModelT]:
        entity = await self.get_by_id(id)
        if entity is None:
            return None
        for key, value in data.items():
            setattr(entity, key, value)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    async def delete(self, id: int) -> bool:
        entity = await self.get_by_id(id)
        if entity is None:
            return False
        await self.session.delete(entity)
        await self.session.commit()
        return True
```

### 5c. Beanie (MongoDB) generic base

Generic over the ID type — a module can use Beanie's default `PydanticObjectId`, or (as Standards does) a custom natural-key string. See Section 10 for why that matters.

```python
# shared/repository/mongo_repository.py
from typing import Generic, TypeVar, Type, Optional, Sequence
from beanie import Document
from app.shared.repository.base import AbstractRepository
from app.shared.specification.base import Specification

DocT = TypeVar("DocT", bound=Document)
IdT = TypeVar("IdT")

class MongoRepository(AbstractRepository[DocT, IdT], Generic[DocT, IdT]):
    model: Type[DocT]

    async def create(self, entity: DocT) -> DocT:
        return await entity.insert()

    async def create_many(self, entities: Sequence[DocT]) -> Sequence[DocT]:
        if not entities:
            return []
        await self.model.insert_many(entities)
        return entities

    async def get_by_id(self, id: IdT) -> Optional[DocT]:
        return await self.model.get(id)

    async def get_many_by_ids(self, ids: Sequence[IdT]) -> Sequence[DocT]:
        if not ids:
            return []
        return await self.model.find({"_id": {"$in": list(ids)}}).to_list()

    async def list(self, skip: int = 0, limit: int = 100) -> Sequence[DocT]:
        return await self.model.find_all().skip(skip).limit(limit).to_list()

    async def find(self, spec: Specification, skip: int = 0, limit: int = 100) -> Sequence[DocT]:
        query = spec.to_mongo(self.model)
        return await self.model.find(query).skip(skip).limit(limit).to_list()

    async def update(self, id: IdT, data: dict) -> Optional[DocT]:
        entity = await self.get_by_id(id)
        if entity is None:
            return None
        await entity.set(data)
        return entity

    async def delete(self, id: IdT) -> bool:
        entity = await self.get_by_id(id)
        if entity is None:
            return False
        await entity.delete()
        return True
```

### 5d. Local file storage (ready for the first upload module)

```python
# storage/base.py
from abc import ABC, abstractmethod
from pathlib import Path
from fastapi import UploadFile

class AbstractFileStorage(ABC):
    @abstractmethod
    async def save(self, file: UploadFile, subfolder: str = "") -> str:
        """Persist the file, return a relative path/key usable to retrieve it later."""

    @abstractmethod
    async def delete(self, relative_path: str) -> bool: ...

    @abstractmethod
    def get_absolute_path(self, relative_path: str) -> Path: ...
```

```python
# storage/local.py
from pathlib import Path
from uuid import uuid4
import aiofiles
from fastapi import UploadFile
from .base import AbstractFileStorage

class LocalFileStorage(AbstractFileStorage):
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def save(self, file: UploadFile, subfolder: str = "") -> str:
        target_dir = self.base_path / subfolder
        target_dir.mkdir(parents=True, exist_ok=True)

        ext = Path(file.filename or "").suffix
        filename = f"{uuid4().hex}{ext}"
        relative_path = f"{subfolder}/{filename}" if subfolder else filename

        async with aiofiles.open(target_dir / filename, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                await out.write(chunk)

        return relative_path

    async def delete(self, relative_path: str) -> bool:
        path = self.base_path / relative_path
        if path.exists():
            path.unlink()
            return True
        return False

    def get_absolute_path(self, relative_path: str) -> Path:
        return self.base_path / relative_path
```

When a future module needs file storage, inject `AbstractFileStorage` into its service alongside its DB repository (two providers composed in one `dependencies.py`, same as any other multi-dependency service) — the service saves the file, then persists its metadata via the DB repo.

---

## 6. Specification Pattern

A `Specification` renders itself two ways — as a SQLAlchemy boolean expression, and as a MongoDB filter dict — so repositories stay ORM-agnostic while supporting rich, dynamic filtering. Composable with `&`, `|`, `~`.

```python
# shared/specification/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

ModelT = TypeVar("ModelT")

class Specification(ABC, Generic[ModelT]):
    @abstractmethod
    def to_sql(self, model: type[ModelT]) -> Any:
        """Return a SQLAlchemy boolean expression, usable in .where(...)."""

    @abstractmethod
    def to_mongo(self, model: type[ModelT]) -> dict:
        """Return a MongoDB filter dict, usable in Model.find(...)."""

    def __and__(self, other: "Specification") -> "AndSpecification":
        return AndSpecification(self, other)

    def __or__(self, other: "Specification") -> "OrSpecification":
        return OrSpecification(self, other)

    def __invert__(self) -> "NotSpecification":
        return NotSpecification(self)


class AndSpecification(Specification):
    def __init__(self, *specs: Specification):
        self.specs = specs

    def to_sql(self, model):
        from sqlalchemy import and_
        return and_(*[s.to_sql(model) for s in self.specs])

    def to_mongo(self, model):
        return {"$and": [s.to_mongo(model) for s in self.specs]}


class OrSpecification(Specification):
    def __init__(self, *specs: Specification):
        self.specs = specs

    def to_sql(self, model):
        from sqlalchemy import or_
        return or_(*[s.to_sql(model) for s in self.specs])

    def to_mongo(self, model):
        return {"$or": [s.to_mongo(model) for s in self.specs]}


class NotSpecification(Specification):
    def __init__(self, spec: Specification):
        self.spec = spec

    def to_sql(self, model):
        from sqlalchemy import not_
        return not_(self.spec.to_sql(model))

    def to_mongo(self, model):
        return {"$nor": [self.spec.to_mongo(model)]}
```

```python
# shared/specification/fields.py
from typing import Any
from .base import Specification

class FieldEquals(Specification):
    """Exact-match filter. `field` may be a dotted path for nested Mongo
    documents (e.g. "standard_metadata.standard_code")."""

    def __init__(self, field: str, value: Any):
        self.field = field
        self.value = value

    def to_sql(self, model):
        return getattr(model, self.field) == self.value

    def to_mongo(self, model):
        return {self.field: self.value}
```

```python
# shared/specification/keyword.py
from typing import Literal
from .base import Specification

class KeywordSpecification(Specification):
    """Match entities where keywords appear (case-insensitive, partial match)
    across a fixed set of fields. `match_mode="any"`: at least one keyword
    hits at least one field. `match_mode="all"`: every keyword must hit at
    least one field (typical for multi-word queries)."""

    def __init__(self, fields: list[str], keywords: list[str], match_mode: Literal["any", "all"] = "any"):
        if not fields:
            raise ValueError("KeywordSpecification requires at least one field")
        self.fields = fields
        self.keywords = [kw.strip() for kw in keywords if kw and kw.strip()]
        self.match_mode = match_mode

    def to_sql(self, model):
        from sqlalchemy import and_, or_, true
        if not self.keywords:
            return true()
        per_keyword = [
            or_(*[getattr(model, field).ilike(f"%{kw}%") for field in self.fields])
            for kw in self.keywords
        ]
        return and_(*per_keyword) if self.match_mode == "all" else or_(*per_keyword)

    def to_mongo(self, model):
        if not self.keywords:
            return {}
        per_keyword = [
            {"$or": [{field: {"$regex": kw, "$options": "i"}} for field in self.fields]}
            for kw in self.keywords
        ]
        return {"$and": per_keyword} if self.match_mode == "all" else {"$or": per_keyword}
```

```python
# shared/specification/match_all.py
from typing import Any
from .base import Specification

class MatchAllSpecification(Specification):
    """No-op specification — matches every record. The identity element for
    folding a dynamic list of optional filters with `&`."""

    def to_sql(self, model) -> Any:
        from sqlalchemy import true
        return true()

    def to_mongo(self, model) -> dict:
        return {}
```

> **Security note**: `fields` must be a fixed allowlist defined by each module's service (e.g. `SEARCHABLE_FIELDS = [...]`), never taken from user input — otherwise a caller could trigger `AttributeError`s against the SQLAlchemy model or query unintended Mongo fields.
>
> **Perf note (Mongo)**: `$regex` scans without an index. For large text-heavy collections, create a MongoDB text index and swap `KeywordSpecification.to_mongo`'s internals for a `$text: {$search: ...}` variant — the `Specification` interface doesn't change.

See `StandardService.list_standards` in Section 9 for `FieldEquals` and `KeywordSpecification` composed together against a real set of optional filters.

---

## 7. DTO & Validation Conventions

- `Create{X}Request` — input for POST. `Update{X}Request` — input for PATCH, every field optional. `{X}Response` — output shape.
- Requests: `model_config = ConfigDict(extra="forbid")` so unknown fields 422 immediately.
- Responses: `model_config = ConfigDict(from_attributes=True)` so they build straight from the entity via `Model.model_validate(entity)`.
- Every field gets an explicit `Field(...)` constraint where one makes sense (`min_length`, `ge`/`le`, etc.) rather than a bare type.
- Always set `response_model=...` on the route — that's what drives the accurate Swagger schema and strips unintended fields, even if the service accidentally returns extra data.
- Bulk operations get their own request/response DTOs (a wrapper `items: list[Create{X}Request]`). Long-running bulk creates may return `202 Accepted` immediately and run inserts in a FastAPI `BackgroundTasks` job — see `CreateManyStandardsRequest` / `CreateManyStandardsAcceptedResponse` in Section 9.
- Derived fields (e.g. `content_hash`, `qdrant_point_id`, timestamps) live on the entity/response, not on create/update requests. The service computes them before persist. Identity fields that must not change later (`standard_code`, `version_year`, `category_table_number`, `ref_number`, and `qdrant_point_id`) are omitted from `Update{X}Request` so `extra="forbid"` 422s any attempt to PATCH them.

---

## 8. Dependency Injection Pattern

Every module's `dependencies.py` follows the same three-step shape: a repository provider, a service provider that depends on it, and an `Annotated` alias the controller uses directly.

```python
# modules/<name>/dependencies.py  (skeleton)
from typing import Annotated
from fastapi import Depends
from .repository import <X>Repository
from .service import <X>Service

def get_<x>_repository(...) -> <X>Repository:
    return <X>Repository(...)

def get_<x>_service(
    repo: Annotated[<X>Repository, Depends(get_<x>_repository)],
) -> <X>Service:
    return <X>Service(repo)

<X>ServiceDep = Annotated[<X>Service, Depends(get_<x>_service)]
```

Postgres-backed repositories additionally depend on `Depends(get_postgres_session)` inside their repository provider (see Section 5b's `__init__(self, session)`); Mongo-backed ones don't need a per-request session since Beanie documents talk to the DB directly. See `StandardService`'s DI wiring in Section 9 for the concrete Mongo case.

**Testing benefit**: because controllers only depend on `<X>ServiceDep`, tests override it with `app.dependency_overrides[get_<x>_service] = lambda: FakeService()` — no real DB or filesystem, ever.

---

## 9. Standards Module — Reference Implementation

The first real module. Mongo-backed, natural-key ID, idempotent create.

Create request matches the upstream document: `_id`, `standard_metadata`, `hierarchy`, `activity`, `parameters`, `specific_requirements`, `searchable_text`. Missing entity fields (`qdrant_point_id`, `content_hash`, `created_at`, `updated_at`) are computed in the service before persist.

`qdrant_point_id` is a **UUID v5** of the entry's immutable identity (`standard_code|version_year|category_table_number|ref_number`) via `generate_qdrant_point_id` in `shared/utils/qdrant.py`. It is never accepted from the request. Concatenating numbers is unsafe (`6.1.3.1`+`2019` and `6.13.1`+`2019` collide); the canonical string + UUID v5 does not. `activity`, `parameters`, and `searchable_text` are attributes, not identity — changing them must not change the Qdrant id.

Identity fields and `qdrant_point_id` are immutable after create. PATCH uses narrower nested DTOs (`UpdateStandardMetadataRequest` / `UpdateStandardHierarchyRequest`) that omit those fields so `extra="forbid"` 422s any attempt to edit them.

```python
# shared/utils/qdrant.py
import uuid

QDRANT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "sc-admin.qdrant")


def generate_qdrant_point_id(entry: dict) -> str:
    """Stable UUID v5 from immutable identity fields — never from a client-supplied id."""
    metadata = entry["standard_metadata"]
    hierarchy = entry["hierarchy"]
    canonical_key = "|".join(
        [
            metadata["standard_code"].strip(),
            metadata["version_year"].strip(),
            hierarchy["category_table_number"].strip(),
            hierarchy["ref_number"].strip(),
        ]
    )
    return str(uuid.uuid5(QDRANT_NAMESPACE, canonical_key))
```

```python
# modules/standards/models.py
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
    qdrant_point_id: str  # UUID v5 of identity fields — computed, never from the request
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
```

```python
# modules/standards/dto.py
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
    """PATCH body for metadata. Identity fields (standard_code, version_year) omitted — extra=forbid 422s them."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    is_latest: bool | None = None


class UpdateStandardHierarchyRequest(BaseModel):
    """PATCH body for hierarchy. Identity fields (category_table_number, ref_number) omitted — extra=forbid 422s them."""
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
    model_config = ConfigDict(extra="forbid")
    items: list[CreateStandardRequest] = Field(..., min_length=1)


class CreateManyStandardsAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["accepted"] = "accepted"
    item_count: int = Field(..., ge=1)
```

```python
# modules/standards/repository.py
from typing import Optional, Sequence
from app.shared.repository.mongo_repository import MongoRepository
from .models import Standard

class StandardRepository(MongoRepository[Standard, str]):
    model = Standard

    async def get_by_qdrant_point_id(self, qdrant_point_id: str) -> Optional[Standard]:
        return await self.model.find_one({"qdrant_point_id": qdrant_point_id})

    async def get_many_by_qdrant_point_ids(self, point_ids: Sequence[str]) -> Sequence[Standard]:
        if not point_ids:
            return []
        return await self.model.find({"qdrant_point_id": {"$in": list(point_ids)}}).to_list()
```

```python
# modules/standards/service.py
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.shared.specification.base import Specification
from app.shared.specification.fields import FieldEquals
from app.shared.specification.keyword import KeywordSpecification
from app.shared.specification.match_all import MatchAllSpecification
from app.shared.utils import generate_qdrant_point_id

from .dto import (
    CreateManyStandardsRequest, CreateStandardRequest, StandardResponse, UpdateStandardRequest,
)
from .models import Standard
from .repository import StandardRepository

SEARCHABLE_FIELDS = ["searchable_text", "activity", "specific_requirements"]
HASH_FIELDS = (
    "standard_metadata", "hierarchy", "activity", "parameters",
    "specific_requirements", "searchable_text",
)


def compute_content_hash(data: dict[str, Any]) -> str:
    canonical = {k: data[k] for k in HASH_FIELDS}
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def point_id_for(payload: CreateStandardRequest) -> str:
    return generate_qdrant_point_id(payload.model_dump())


class StandardService:
    def __init__(self, repository: StandardRepository):
        self.repository = repository

    def reject_duplicate_keys(self, payload: CreateManyStandardsRequest) -> None:
        ids = [item.id for item in payload.items]
        if len(ids) != len(set(ids)):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Duplicate ids within the same request batch")
        point_ids = [point_id_for(item) for item in payload.items]
        if len(point_ids) != len(set(point_ids)):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Duplicate qdrant_point_id values within the same request batch",
            )

    async def _ensure_point_id_free(self, qdrant_point_id: str, owner_id: str) -> None:
        occupant = await self.repository.get_by_qdrant_point_id(qdrant_point_id)
        if occupant is not None and occupant.id != owner_id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"qdrant_point_id {qdrant_point_id} is already used by '{occupant.id}'",
            )

    def _entity_from_create(self, payload: CreateStandardRequest, now: datetime) -> Standard:
        data = payload.model_dump()
        return Standard(
            **data,
            qdrant_point_id=generate_qdrant_point_id(data),
            content_hash=compute_content_hash(data),
            created_at=now,
            updated_at=now,
        )

    async def create_standard(self, payload: CreateStandardRequest) -> StandardResponse:
        content_hash = compute_content_hash(payload.model_dump())
        existing = await self.repository.get_by_id(payload.id)

        if existing is not None:
            if existing.content_hash == content_hash:
                return StandardResponse.model_validate(existing)  # idempotent no-op
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Standard '{payload.id}' already exists with different content. "
                f"Use PATCH /standards/{payload.id} to update it explicitly.",
            )

        qdrant_point_id = point_id_for(payload)
        await self._ensure_point_id_free(qdrant_point_id, payload.id)

        now = datetime.now(timezone.utc)
        standard = self._entity_from_create(payload, now)
        try:
            created = await self.repository.create(standard)
        except DuplicateKeyError:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"qdrant_point_id {qdrant_point_id} is already used",
            )
        return StandardResponse.model_validate(created)

    async def create_many_standards(self, payload: CreateManyStandardsRequest) -> None:
        """Runs after POST /bulk returns 202. Duplicate keys in the payload were already rejected."""
        ids = [item.id for item in payload.items]
        point_ids = [point_id_for(item) for item in payload.items]
        existing_by_id = {s.id: s for s in await self.repository.get_many_by_ids(ids)}
        existing_by_point = {
            s.qdrant_point_id: s
            for s in await self.repository.get_many_by_qdrant_point_ids(point_ids)
        }

        now = datetime.now(timezone.utc)
        to_insert: list[Standard] = []
        for item in payload.items:
            current = existing_by_id.get(item.id)
            if current is not None:
                continue  # same-hash retry or content conflict — neither is inserted
            occupant = existing_by_point.get(point_id_for(item))
            if occupant is not None:
                continue  # point_id taken by another document — skip (HTTP already returned)
            to_insert.append(self._entity_from_create(item, now))

        if not to_insert:
            return
        try:
            await self.repository.create_many(to_insert)
        except DuplicateKeyError:
            pass  # unique index race; in-process background job has no caller to 409

    async def get_standard(self, standard_id: str) -> StandardResponse:
        standard = await self.repository.get_by_id(standard_id)
        if standard is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Standard not found")
        return StandardResponse.model_validate(standard)

    async def list_standards(
        self,
        standard_code: str | None,
        version_year: str | None,
        is_latest: bool | None,
        category_table_number: str | None,
        activity: str | None,
        keywords: list[str],
        match_mode: Literal["any", "all"],
        skip: int,
        limit: int,
    ) -> list[StandardResponse]:
        filters: list[Specification] = []
        if standard_code:
            filters.append(FieldEquals("standard_metadata.standard_code", standard_code))
        if version_year:
            filters.append(FieldEquals("standard_metadata.version_year", version_year))
        if is_latest is not None:
            filters.append(FieldEquals("standard_metadata.is_latest", is_latest))
        if category_table_number:
            filters.append(FieldEquals("hierarchy.category_table_number", category_table_number))
        if activity:
            filters.append(FieldEquals("activity", activity))
        if keywords:
            filters.append(KeywordSpecification(fields=SEARCHABLE_FIELDS, keywords=keywords, match_mode=match_mode))

        spec: Specification = MatchAllSpecification()
        for f in filters:
            spec = spec & f

        standards = await self.repository.find(spec, skip=skip, limit=limit)
        return [StandardResponse.model_validate(s) for s in standards]

    async def update_standard(self, standard_id: str, payload: UpdateStandardRequest) -> StandardResponse:
        existing = await self.repository.get_by_id(standard_id)
        if existing is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Standard not found")

        data = payload.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields provided to update")

        existing_dump = existing.model_dump()
        if "standard_metadata" in data:
            data["standard_metadata"] = {**existing_dump["standard_metadata"], **data["standard_metadata"]}
        if "hierarchy" in data:
            data["hierarchy"] = {**existing_dump["hierarchy"], **data["hierarchy"]}

        merged = {**existing_dump, **data}
        data["content_hash"] = compute_content_hash(merged)
        data["updated_at"] = datetime.now(timezone.utc)
        # identity fields and qdrant_point_id are never in `data`

        updated = await self.repository.update(standard_id, data)
        return StandardResponse.model_validate(updated)

    async def delete_standard(self, standard_id: str) -> None:
        if not await self.repository.delete(standard_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Standard not found")
```

```python
# modules/standards/controller.py
from typing import Literal
from fastapi import APIRouter, BackgroundTasks, Query, status

from .dependencies import StandardServiceDep
from .dto import (
    CreateManyStandardsAcceptedResponse, CreateManyStandardsRequest,
    CreateStandardRequest, StandardResponse, UpdateStandardRequest,
)

router = APIRouter(prefix="/standards", tags=["Standards"])


@router.post("/", response_model=StandardResponse, status_code=status.HTTP_201_CREATED)
async def create_standard(payload: CreateStandardRequest, service: StandardServiceDep):
    return await service.create_standard(payload)


@router.post("/bulk", response_model=CreateManyStandardsAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_many_standards(
    payload: CreateManyStandardsRequest,
    service: StandardServiceDep,
    background_tasks: BackgroundTasks,
):
    service.reject_duplicate_keys(payload)
    background_tasks.add_task(service.create_many_standards, payload)
    return CreateManyStandardsAcceptedResponse(item_count=len(payload.items))


@router.get("/", response_model=list[StandardResponse])
async def list_standards(
    service: StandardServiceDep,
    standard_code: str | None = Query(default=None),
    version_year: str | None = Query(default=None),
    is_latest: bool | None = Query(default=None),
    category_table_number: str | None = Query(default=None),
    activity: str | None = Query(default=None),
    keywords: list[str] = Query(default=[]),
    match_mode: Literal["any", "all"] = Query(default="any"),
    skip: int = 0,
    limit: int = 100,
):
    return await service.list_standards(
        standard_code, version_year, is_latest, category_table_number,
        activity, keywords, match_mode, skip, limit,
    )


# NOTE: static paths ("/bulk" above) must be declared before "/{standard_id}" —
# otherwise FastAPI matches them as the path parameter instead.
@router.get("/{standard_id}", response_model=StandardResponse)
async def get_standard(standard_id: str, service: StandardServiceDep):
    return await service.get_standard(standard_id)


@router.patch("/{standard_id}", response_model=StandardResponse)
async def update_standard(standard_id: str, payload: UpdateStandardRequest, service: StandardServiceDep):
    return await service.update_standard(standard_id, payload)


@router.delete("/{standard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_standard(standard_id: str, service: StandardServiceDep):
    await service.delete_standard(standard_id)
```

```python
# modules/standards/dependencies.py
from typing import Annotated
from fastapi import Depends
from .repository import StandardRepository
from .service import StandardService


def get_standard_repository() -> StandardRepository:
    return StandardRepository()


def get_standard_service(
    repo: Annotated[StandardRepository, Depends(get_standard_repository)],
) -> StandardService:
    return StandardService(repo)


StandardServiceDep = Annotated[StandardService, Depends(get_standard_service)]
```

---

## 10. Idempotency, uniqueness, and bulk create

The `id` field (e.g. `"en12464_1_v2019_6_1_1"`) is a **deterministic natural key** — the upstream source derives it from the standard's identity (code + version + ref number), not a random surrogate. It's used directly as Beanie's `id`/Mongo's `_id`, which means the database itself guarantees no two documents can ever share it. The create request sends it as `_id` (Pydantic alias).

`content_hash` is **computed** by the service (SHA-256 of canonical JSON over `HASH_FIELDS`: metadata, hierarchy, activity, parameters, specific_requirements, searchable_text). It is never a request field. `qdrant_point_id` is **not** in the hash — it is a separate unique identity, a UUID v5 of `standard_code|version_year|category_table_number|ref_number` via `generate_qdrant_point_id`. It is never a request field.

`qdrant_point_id` is unique (`IndexModel(..., unique=True)` plus a pre-insert lookup). Two documents that hash to the same identity (same four fields, different `_id`) are **`409 Conflict`**. PATCH cannot change the point id or those four identity fields (`UpdateStandardRequest` / nested update DTOs omit them).

| Situation | Outcome |
| --- | --- |
| No document with this `id`, computed `qdrant_point_id` free | **Insert.** Hash, timestamps, and UUID v5 point id computed. |
| Same `id`, **same** computed `content_hash` | **No-op success**, existing record returned. Safe retry. Stored point id is kept. |
| Same `id`, **different** computed `content_hash` | **`409 Conflict`.** Caller must `PATCH /standards/{id}` (cannot change identity fields). |
| New `id`, computed `qdrant_point_id` already used by another document | **`409 Conflict`.** Unique index is the race backstop (`DuplicateKeyError` → 409). |
| Duplicate `id`s **or** duplicate computed `qdrant_point_id`s (same identity fields) inside one `create_many` payload | **`400 Bad Request`.** Client-side bug, rejected before the background job is queued. |

`POST /standards/bulk` validates the batch (schema + `reject_duplicate_keys`) then returns **`202 Accepted`** with `{status: "accepted", item_count: N}` and runs `create_many_standards` in a FastAPI `BackgroundTasks` job. The worker applies the same per-item insert/skip rules but **does not** report outcomes back — the HTTP response has already been sent.

> Ceiling: `BackgroundTasks` are in-process; a crash loses the job and there is no status endpoint. Upgrade to a real queue (or a job document) if bulk ingest must be durable.

This pattern (natural key as the DB id + a computed content fingerprint + a UUID v5 point id from immutable identity fields) generalizes to any future module ingesting externally-sourced, re-importable data. For modules where the DB should own identity, skip this — a normal auto-generated ID with a plain `create`/`409-if-exists` is enough.

---

## 11. Adding a New Module — Checklist

1. Create `modules/<name>/` with the six files: `models.py`, `dto.py`, `repository.py`, `service.py`, `controller.py`, `dependencies.py`.
2. **`models.py`**: define the entity — a Beanie `Document` (Mongo) or a `Mapped[...]` SQLAlchemy class (Postgres). Decide the ID strategy up front (auto-generated vs. natural key) — it determines whether you need Standards-style idempotency logic.
3. **`dto.py`**: `Create{X}Request`, `Update{X}Request` (all optional), `{X}Response`, plus bulk variants if needed. `extra="forbid"` + explicit `Field` constraints on everything. Derived fields (`content_hash`, `qdrant_point_id`, timestamps) and immutable identity fields stay off the request models they don't belong on.
4. **`repository.py`**: subclass `SQLRepository[Model]` or `MongoRepository[Model, IdType]`, set `model = ...`, add custom queries only if `find(spec)` genuinely can't express them.
5. **`service.py`**: business logic only — DTO↔entity mapping, idempotency/business rules, `HTTPException` for domain errors (404/409/etc). Define a `SEARCHABLE_FIELDS` allowlist here if the module needs keyword search.
6. **`controller.py`**: thin routes, `response_model` on every one, delegate to the service via its `*ServiceDep` alias. Static paths (`/search`, `/bulk`) before `/{id}` paths.
7. **`dependencies.py`**: `get_<x>_repository` → `get_<x>_service` → `<X>ServiceDep`.
8. Register the router in `main.py`. If Mongo: add the `Document` class to `init_beanie(document_models=[...])` in `db/mongo/client.py`. If Postgres: generate an Alembic migration.
9. Add tests mirroring `tests/modules/standards/` — in-memory fakes only (Section 15). Never point tests at a real database or directory.

---

## 12. App Wiring & DB Lifecycle

```python
# core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "CRUD API"
    ENV: str = "local"

    MONGO_URI: str
    MONGO_DB_NAME: str = "app"

    POSTGRES_DSN: str | None = None  # not used yet — make required once the first SQL module lands

    LOCAL_STORAGE_PATH: str = "./uploads"

settings = Settings()
```

```python
# db/mongo/client.py
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.core.config import settings
from app.modules.standards.models import Standard  # add every new Mongo module's Document here

_client: AsyncIOMotorClient | None = None

async def init_mongo() -> None:
    global _client
    _client = AsyncIOMotorClient(settings.MONGO_URI)
    await init_beanie(database=_client[settings.MONGO_DB_NAME], document_models=[Standard])

async def close_mongo() -> None:
    if _client:
        _client.close()
```

```python
# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings
from app.db.mongo.client import init_mongo, close_mongo
from app.modules.standards.controller import router as standards_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_mongo()
    yield
    await close_mongo()
    # once the first Postgres module exists: import the engine and `await engine.dispose()` here too

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.include_router(standards_router, prefix="/api/v1")
```

Postgres tables (when the first SQL module arrives) are managed via **Alembic** migrations against `app.db.postgres.base.Base.metadata`. Mongo needs none — Beanie just needs every `Document` subclass listed in `init_beanie(document_models=[...])`.

---

## 13. Consistent Error Responses (also visible in Swagger)

```python
# shared/dto/error.py
from pydantic import BaseModel

class ErrorResponse(BaseModel):
    detail: str
```

The examples in Section 9 raise `HTTPException` directly, which FastAPI already turns into a `{"detail": "..."}` JSON body — consistent with `ErrorResponse` above. For per-route Swagger documentation of error shapes, add `responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}}` to route decorators as needed.

---

## 14. Local Dev Infra

```yaml
# docker-compose.yml
version: '3.9'
services:
  mongo:
    image: mongo:7
    ports: ['27017:27017']
    volumes: ['mongodata:/data/db']

  # postgres:                # uncomment once the first SQL-backed module exists
  #   image: postgres:16
  #   environment:
  #     POSTGRES_USER: app
  #     POSTGRES_PASSWORD: app
  #     POSTGRES_DB: app
  #   ports: ["5432:5432"]
  #   volumes: ["pgdata:/var/lib/postgresql/data"]

volumes:
  mongodata:
  # pgdata:
```

```bash
# .env
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=app
LOCAL_STORAGE_PATH=./uploads
```

---

## 15. Testing Strategy

**Hard rule: tests must not persist anything.** No Mongo, no Postgres, no files on disk, no TestClient lifespan that calls `init_mongo`. A fake in-memory repository (a dict behind `AbstractRepository`) is the only store. If a test would need a real database or `./uploads` to pass, the test is wrong.

- **Service tests**: inject a `FakeStandardRepository`. Assert the happy path (computed `content_hash` / `qdrant_point_id` / timestamps, idempotent skip) and the error path (`HTTPException` 400/404/409). Nothing is written outside the fake.
  - Create payload has `_id` and **no** `content_hash` or `qdrant_point_id`; the entity the fake received has a computed hash, UUID v5 point id, and timestamps.
  - `create_standard` called twice with identical content → second call returns the existing record, fake `create` is not called again.
  - `create_standard` with the same `id` but different content → `409`.
  - `create_standard` with a new `id` but the same identity fields (same computed `qdrant_point_id`) → `409`.
  - PATCH of content recomputes the hash and leaves `qdrant_point_id` and identity fields untouched.
  - `reject_duplicate_keys` with a repeated `id` or a repeated computed `qdrant_point_id` in one payload → `400`.
  - `create_many_standards` (the worker) inserts only genuinely new items into the fake; same-id retries and taken point ids are skipped.
- **Controller tests**: `httpx.AsyncClient` against an app that **does not** run the production lifespan, with `app.dependency_overrides[get_standard_service] = lambda: FakeStandardService()`. Assert status codes and response bodies (flow + errors). Pydantic 422s (unknown fields, `qdrant_point_id` on create, identity fields / `qdrant_point_id` / `content_hash` on PATCH) live here. `POST /bulk` returns **202** with `item_count` without waiting on inserts.
- **Helper tests**: `generate_qdrant_point_id` is stable for the same identity, differs for `6.1|6.1.3.1` vs `6.13|6.13.1`, and ignores `activity`.
- **No repository/integration tests against a live engine.** Unique indexes and query plans are not the unit-test suite's job. Docker Compose is for local *running* of the app, not for pytest.

---

## 16. Where Auth Plugs In Later

Not implemented now, but the seam to leave alone:

```python
# core/dependencies.py (future)
async def get_current_user() -> User:
    raise NotImplementedError  # placeholder
```

Once implemented, protected routes add `user: Annotated[User, Depends(get_current_user)]` to controller signatures — no change needed to services/repositories, since authorization checks belong in the **service** layer, not the repository.

---

## 17. Getting Started Checklist

1. `pip install` the packages from Section 2.
2. `docker compose up -d` for local Mongo.
3. Scaffold `core/`, `db/`, `storage/`, `shared/` as in Section 3.
4. Build `modules/standards/` from Section 9's code.
5. Wire `main.py` + `db/mongo/client.py` (Section 12), confirm Swagger UI at `/docs` shows accurate, strict schemas for every Standards route.
6. Add error handling (Section 13).
7. Add tests (Section 15) as you go, not after — in-memory fakes only, never against the compose Mongo or `./uploads`.
8. For each new module going forward, follow Section 11's checklist.

---

## 18. Roadmap

- First Postgres-backed module, using Section 5b's `SQLRepository` the same way Standards uses `MongoRepository`.
- Auth (JWT or session-based) + `get_current_user` + per-route scopes.
- Generic `Page[T]` response wrapper for consistent pagination metadata (`total`, `skip`, `limit`) once list endpoints need it.
- Mongo text index + `$text` search for `Standard.searchable_text` if `$regex` scanning becomes a bottleneck.
- First file-upload module using `AbstractFileStorage`, swappable to `S3FileStorage` later.
- Structured logging + request ID middleware.
