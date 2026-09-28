# FastAPI Modular CRUD Architecture — Repository Pattern (Dual ORM + Local File Storage)

**Standards is the first HTTP module (Mongo).** Assets is the first file-upload module. Fixtures is the first nested Postgres CRUD module (asset UUIDs, not uploads). Mirror Standards for JSON HTTP shape, assets for files, and assets/fixtures for SQL persistence — see Section 11.

## 1. Goals & Constraints

- **Layers**: `Controller → Service → Repository → (Postgres | MongoDB | Local FS)`. Services hold business logic; controllers stay thin (validation + delegation); repositories only know how to talk to a single data source.
- **Two ORMs, one pattern**: SQLAlchemy 2.x (async) for Postgres, Beanie (async, built on Motor + Pydantic) for MongoDB. Both are hidden behind the same repository abstraction so services never import `sqlalchemy` or `beanie` directly.
- **File uploads are a repository too**: `AbstractFileStorage` / `LocalFileStorage`. Assets injects it next to `AssetRepository`. Swap for S3/GCS later without touching the service.
- **Feature-based modules**: every domain concept lives in its own folder with `controller.py`, `service.py`, `repository.py`, `models.py` (ORM/ODM entities), `dto.py` (Pydantic schemas), `dependencies.py` (DI wiring).
- **Consistent JSON envelope**: successes are `{success: true, data, pagination}` (`ApiResponse[T]`). Collection GET fills pagination from `page`/`limit` query params; other JSON routes set `pagination` to `null`. Errors stay `{detail: ...}`; DELETE stays 204. **Exception**: `GET /assets/{id}` returns the file stream (`StreamingResponse`), not the envelope.
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

# Postgres (SQLAlchemy async) — used by assets + fixtures
sqlalchemy>=2
asyncpg
alembic

# MongoDB
beanie>=1.26,<2         # Beanie 2 dropped Motor; pin below 2
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
  sqlalchemy asyncpg alembic "beanie>=1.26,<2" motor \
  python-multipart aiofiles \
  pytest pytest-asyncio httpx ruff mypy
```

---

## 3. Folder Structure

```
alembic.ini                     # Alembic config — DSN comes from Settings, not this file
alembic/
├── env.py                       # async engine, Base.metadata, imports SQL module models
├── script.py.mako
└── versions/
    └── 0001_assets_fixtures.py  # assets + fixture tables
app/
├── main.py                      # app factory, router registration, lifespan
├── core/
│   ├── config.py                 # pydantic-settings Settings
│   ├── exceptions.py             # domain exceptions + handlers
│   └── logging.py
├── db/
│   ├── postgres/
│   │   ├── base.py                # SQLAlchemy declarative Base
│   │   └── session.py             # async engine + session dependency + dispose_postgres()
│   └── mongo/
│       └── client.py              # Motor client + init_beanie()
├── storage/
│   ├── base.py                    # AbstractFileStorage — save, delete, iter_bytes, get_absolute_path
│   └── local.py                   # LocalFileStorage (LOCAL_STORAGE_PATH)
├── shared/
│   ├── dto/
│   │   ├── error.py                # ErrorResponse schema
│   │   ├── pagination.py           # PaginationQuery (page, limit) + PaginationMeta
│   │   └── response.py             # ApiResponse[T] — {success, data, pagination}
│   ├── specification/
│   │   ├── base.py                 # Specification[Model] — ORM-agnostic composable criteria
│   │   ├── fields.py               # FieldEquals, ArrayContains
│   │   ├── keyword.py              # KeywordSpecification — multi-field keyword search
│   │   └── match_all.py            # MatchAllSpecification — identity element for dynamic filters
│   ├── utils/
│   │   └── qdrant.py               # UUID v5 qdrant point id from identity fields
│   └── repository/
│       ├── base.py                 # AbstractRepository[Entity, ID]
│       ├── sql_repository.py       # generic SQLAlchemy CRUD base
│       └── mongo_repository.py     # generic Beanie CRUD base
├── modules/
│   ├── standards/                  # Mongo HTTP module — mirror this shape for new HTTP modules
│   │   ├── controller.py
│   │   ├── service.py
│   │   ├── repository.py
│   │   ├── models.py
│   │   ├── dto.py
│   │   └── dependencies.py
│   ├── assets/                     # shared file-catalog (Postgres + local FS)
│   │   ├── models.py
│   │   ├── repository.py
│   │   ├── dto.py
│   │   ├── service.py
│   │   ├── controller.py
│   │   └── dependencies.py
│   └── fixtures/                   # Postgres catalog — JSON CRUD, asset UUID FKs
│       ├── models.py
│       ├── repository.py
│       ├── dto.py
│       ├── service.py
│       ├── controller.py
│       └── dependencies.py
└── tests/                       # in-memory only — never a real DB or filesystem (Section 15)
    ├── conftest.py              # dummy Beanie document settings; no init_mongo
    ├── shared/
    │   ├── test_pagination.py
    │   ├── test_qdrant.py
    │   └── test_specification.py
    └── modules/
        ├── standards/...
        ├── assets/...
        └── fixtures/...
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
    async def count(self, spec: Specification) -> int: ...

    @abstractmethod
    async def update(self, id: IdT, data: dict) -> Optional[EntityT]: ...

    @abstractmethod
    async def delete(self, id: IdT) -> bool: ...
```

### 5b. SQLAlchemy (Postgres) generic base

Assumes every SQLAlchemy model exposes its primary key as `.id`. Generic over the ID type (assets/fixtures use `uuid.UUID`). Subclasses override `_options()` with `selectinload(...)` so async code never lazy-loads. `create` / `update` re-fetch via `get_by_id` so those options apply ( `refresh` does not populate relationships). `get_one(spec)` is the unique-lookup helper (e.g. `relative_path`).

```python
# shared/repository/sql_repository.py
from typing import Any, Generic, TypeVar, Type, Optional, Sequence
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.repository.base import AbstractRepository
from app.shared.specification.base import Specification

ModelT = TypeVar("ModelT")
IdT = TypeVar("IdT")

class SQLRepository(AbstractRepository[ModelT, IdT], Generic[ModelT, IdT]):
    model: Type[ModelT]

    def __init__(self, session: AsyncSession):
        self.session = session

    def _options(self) -> Sequence[Any]:
        return ()

    def _select(self):
        return select(self.model).options(*self._options())

    async def create(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.commit()
        loaded = await self.get_by_id(entity.id)
        return loaded if loaded is not None else entity

    async def create_many(self, entities: Sequence[ModelT]) -> Sequence[ModelT]:
        if not entities:
            return []
        self.session.add_all(entities)
        await self.session.commit()
        return await self.get_many_by_ids([entity.id for entity in entities])

    async def get_by_id(self, id: IdT) -> Optional[ModelT]:
        return await self.session.get(self.model, id, options=self._options())

    async def get_many_by_ids(self, ids: Sequence[IdT]) -> Sequence[ModelT]:
        if not ids:
            return []
        result = await self.session.execute(self._select().where(self.model.id.in_(ids)))
        rows = result.scalars().all()
        by_id = {row.id: row for row in rows}
        return [by_id[i] for i in ids if i in by_id]

    async def list(self, skip: int = 0, limit: int = 100) -> Sequence[ModelT]:
        result = await self.session.execute(self._select().offset(skip).limit(limit))
        return result.scalars().all()

    async def find(self, spec: Specification, skip: int = 0, limit: int = 100) -> Sequence[ModelT]:
        stmt = self._select().where(spec.to_sql(self.model)).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_one(self, spec: Specification) -> Optional[ModelT]:
        rows = await self.find(spec, skip=0, limit=1)
        return rows[0] if rows else None

    async def count(self, spec: Specification) -> int:
        stmt = select(func.count()).select_from(self.model).where(spec.to_sql(self.model))
        return await self.session.scalar(stmt) or 0

    async def update(self, id: IdT, data: dict) -> Optional[ModelT]:
        entity = await self.session.get(self.model, id)
        if entity is None:
            return None
        for key, value in data.items():
            setattr(entity, key, value)
        await self.session.commit()
        return await self.get_by_id(id)

    async def delete(self, id: IdT) -> bool:
        entity = await self.session.get(self.model, id)
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

    async def count(self, spec: Specification) -> int:
        query = spec.to_mongo(self.model)
        return await self.model.find(query).count()

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

### 5d. Local file storage (used by assets)

`save` returns `(relative_path, size_bytes)` counted while writing. `iter_bytes` streams reads and raises `FileNotFoundError` if the key is missing. `get_absolute_path` must refuse paths that escape the storage root.

```python
# storage/base.py
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path
from fastapi import UploadFile

class AbstractFileStorage(ABC):
    @abstractmethod
    async def save(self, file: UploadFile, subfolder: str = "") -> tuple[str, int]:
        """Persist the file. Return (relative path/key, size in bytes)."""

    @abstractmethod
    async def delete(self, relative_path: str) -> bool: ...

    @abstractmethod
    def get_absolute_path(self, relative_path: str) -> Path: ...

    @abstractmethod
    def iter_bytes(self, relative_path: str) -> AsyncIterator[bytes]:
        """Yield file bytes. Raise FileNotFoundError if missing."""
```

`LocalFileStorage` writes under `LOCAL_STORAGE_PATH` with a uuid filename (keeps the original suffix), reads/writes in 1MiB aiofiles chunks, and guards `get_absolute_path` with `is_relative_to`.

Assets injects `AbstractFileStorage` next to `AssetRepository` in `dependencies.py`. The service saves under subfolder `assets`, then inserts the `Asset` row; if the DB write fails it deletes the stored file. Tests use an in-memory `FakeFileStorage` — never `LocalFileStorage` (its `__init__` mkdir's the root).

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


class ArrayContains(Specification):
    """True when array column `field` contains `value` (Postgres `@>`, Mongo element match)."""

    def __init__(self, field: str, value: Any):
        self.field = field
        self.value = value

    def to_sql(self, model):
        return getattr(model, self.field).contains([self.value])

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

See `StandardService.list_standards` in Section 9 for `FieldEquals` and `KeywordSpecification` composed together. Fixtures use `ArrayContains` for `TEXT[]` tags (`applications`, protections).

---

## 7. DTO & Validation Conventions

- `Create{X}Request` — input for POST. `Update{X}Request` — input for PATCH, every field optional. `{X}Response` — output shape.
- Requests: `model_config = ConfigDict(extra="forbid")` so unknown fields 422 immediately.
- Responses: `model_config = ConfigDict(from_attributes=True)` so they build straight from the entity via `Model.model_validate(entity)`.
- Every field gets an explicit `Field(...)` constraint where one makes sense (`min_length`, `ge`/`le`, etc.) rather than a bare type.
- Always set `response_model=...` on the route — that's what drives the accurate Swagger schema and strips unintended fields, even if the service accidentally returns extra data.
- JSON successes wrap in `ApiResponse[T]` (`shared/dto/response.py`): `{success: true, data: T, pagination: PaginationMeta | null}`. `data` is whatever that route used to return. Collection GET fills `pagination`; other JSON routes set it to `null`. `HTTPException` and Pydantic 422 stay `{detail: ...}` — not this envelope. DELETE stays 204 with no body.
- Collection GET takes `PaginationQuery` (`page` ≥ 1, `limit` 1–1000, defaults 1 / 100) as query params. Inject with `Annotated[PaginationQuery, Depends()]` — `Query()` on the model 422s. Storage still uses `skip`/`limit`; `PaginationQuery.skip` is `(page - 1) * limit`. `page_size` in the meta is the request `limit`. List services return `(items, total_count)` so the controller can build `PaginationMeta.from_query`.
- Bulk operations get their own request/response DTOs (a wrapper `items: list[Create{X}Request]`). Long-running bulk creates may return `202 Accepted` immediately and run inserts in a FastAPI `BackgroundTasks` job — see `CreateManyStandardsRequest` / `CreateManyStandardsAcceptedResponse` in Section 9.
- Derived fields (e.g. `content_hash`, `qdrant_point_id`, timestamps) live on the entity/response, not on create/update requests. The service computes them before persist. Identity fields that must not change later (`standard_code`, `version_year`, `category_table_number`, `ref_number`, and `qdrant_point_id`) are omitted from `Update{X}Request` so `extra="forbid"` 422s any attempt to PATCH them.

```python
# shared/dto/pagination.py
from math import ceil
from pydantic import BaseModel, Field

class PaginationQuery(BaseModel):
    page: int = Field(1, ge=1)
    limit: int = Field(100, ge=1, le=1000)

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.limit


class PaginationMeta(BaseModel):
    total_count: int = Field(..., ge=0)
    page_size: int = Field(..., ge=1)
    current_page: int = Field(..., ge=1)
    total_pages: int = Field(..., ge=0)

    @classmethod
    def from_query(cls, total_count: int, page: int, limit: int) -> "PaginationMeta":
        total_pages = ceil(total_count / limit) if total_count else 0
        return cls(total_count=total_count, page_size=limit, current_page=page, total_pages=total_pages)
```

```python
# shared/dto/response.py
from typing import Generic, Literal, TypeVar
from pydantic import BaseModel
from app.shared.dto.pagination import PaginationMeta

T = TypeVar("T")

class ApiResponse(BaseModel, Generic[T]):
    success: Literal[True] = True
    data: T
    pagination: PaginationMeta | None = None
```

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

`GET /standards/categories` is a static path (before `/{standard_id}`) returning distinct `(standard_metadata, category_table_number, category_title)` — one row per `(standard_code, version_year, category_table_number)`. Optional `standard_code` / `version_year` / `is_latest` match list. No pagination (`pagination` is `null`); the set is small.

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


class StandardCategoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    standard_metadata: StandardMetadataDTO
    category_table_number: str = Field(..., min_length=1)
    category_title: str = Field(..., min_length=1)


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
from app.shared.specification.base import Specification
from .models import Standard, StandardMetadata

class StandardRepository(MongoRepository[Standard, str]):
    model = Standard

    async def get_by_qdrant_point_id(self, qdrant_point_id: str) -> Optional[Standard]:
        return await self.model.find_one({"qdrant_point_id": qdrant_point_id})

    async def get_many_by_qdrant_point_ids(self, point_ids: Sequence[str]) -> Sequence[Standard]:
        if not point_ids:
            return []
        return await self.model.find({"qdrant_point_id": {"$in": list(point_ids)}}).to_list()

    async def distinct_categories(self, spec: Specification) -> Sequence[tuple[StandardMetadata, str, str]]:
        # ponytail: unbounded $group; lighting standards have tens of tables. Paginate if this becomes a huge cross-standard dump.
        pipeline: list[dict] = []
        match = spec.to_mongo(self.model)
        if match:
            pipeline.append({"$match": match})
        pipeline.append({
            "$group": {
                "_id": {
                    "standard_code": "$standard_metadata.standard_code",
                    "version_year": "$standard_metadata.version_year",
                    "category_table_number": "$hierarchy.category_table_number",
                },
                "category_title": {"$first": "$hierarchy.category_title"},
                "is_latest": {"$first": "$standard_metadata.is_latest"},
            }
        })
        rows = await self.model.aggregate(pipeline).to_list()
        return [
            (
                StandardMetadata(
                    standard_code=row["_id"]["standard_code"],
                    version_year=row["_id"]["version_year"],
                    is_latest=row["is_latest"],
                ),
                row["_id"]["category_table_number"],
                row["category_title"],
            )
            for row in rows
        ]
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
    CreateManyStandardsRequest, CreateStandardRequest, StandardCategoryResponse,
    StandardMetadataDTO, StandardResponse, UpdateStandardRequest,
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
    ) -> tuple[list[StandardResponse], int]:
        spec = self._list_spec(
            standard_code, version_year, is_latest, category_table_number,
            activity, keywords, match_mode,
        )
        total = await self.repository.count(spec)
        standards = await self.repository.find(spec, skip=skip, limit=limit)
        return [StandardResponse.model_validate(s) for s in standards], total

    async def list_categories(
        self,
        standard_code: str | None,
        version_year: str | None,
        is_latest: bool | None,
    ) -> list[StandardCategoryResponse]:
        spec = self._list_spec(standard_code, version_year, is_latest, None, None, [], "any")
        rows = await self.repository.distinct_categories(spec)
        items = [
            StandardCategoryResponse(
                standard_metadata=StandardMetadataDTO.model_validate(meta),
                category_table_number=table_number,
                category_title=title,
            )
            for meta, table_number, title in rows
        ]

        def _key(item: StandardCategoryResponse) -> tuple:
            parts = tuple(int(p) if p.isdigit() else p for p in item.category_table_number.split("."))
            return (item.standard_metadata.standard_code, item.standard_metadata.version_year, parts)

        items.sort(key=_key)
        return items

    def _list_spec(
        self,
        standard_code: str | None,
        version_year: str | None,
        is_latest: bool | None,
        category_table_number: str | None,
        activity: str | None,
        keywords: list[str],
        match_mode: Literal["any", "all"],
    ) -> Specification:
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
        return spec

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
from typing import Annotated, Literal
from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.shared.dto.error import ErrorResponse
from app.shared.dto.pagination import PaginationMeta, PaginationQuery
from app.shared.dto.response import ApiResponse
from .dependencies import StandardServiceDep
from .dto import (
    CreateManyStandardsAcceptedResponse, CreateManyStandardsRequest,
    CreateStandardRequest, StandardCategoryResponse, StandardResponse, UpdateStandardRequest,
)

router = APIRouter(prefix="/standards", tags=["Standards"])

RESP_400 = {status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse}}
RESP_404 = {status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}}
RESP_409 = {status.HTTP_409_CONFLICT: {"model": ErrorResponse}}


@router.post("/", response_model=ApiResponse[StandardResponse], status_code=status.HTTP_201_CREATED, responses={**RESP_409})
async def create_standard(payload: CreateStandardRequest, service: StandardServiceDep):
    return ApiResponse(data=await service.create_standard(payload))


@router.post("/bulk", response_model=ApiResponse[CreateManyStandardsAcceptedResponse], status_code=status.HTTP_202_ACCEPTED, responses={**RESP_400})
async def create_many_standards(
    payload: CreateManyStandardsRequest,
    service: StandardServiceDep,
    background_tasks: BackgroundTasks,
):
    service.reject_duplicate_keys(payload)
    background_tasks.add_task(service.create_many_standards, payload)
    return ApiResponse(data=CreateManyStandardsAcceptedResponse(item_count=len(payload.items)))


@router.get("/", response_model=ApiResponse[list[StandardResponse]])
async def list_standards(
    service: StandardServiceDep,
    pagination: Annotated[PaginationQuery, Depends()],
    standard_code: str | None = Query(default=None),
    version_year: str | None = Query(default=None),
    is_latest: bool | None = Query(default=None),
    category_table_number: str | None = Query(default=None),
    activity: str | None = Query(default=None),
    keywords: list[str] = Query(default=[]),
    match_mode: Literal["any", "all"] = Query(default="any"),
):
    items, total = await service.list_standards(
        standard_code, version_year, is_latest, category_table_number,
        activity, keywords, match_mode, pagination.skip, pagination.limit,
    )
    return ApiResponse(
        data=items,
        pagination=PaginationMeta.from_query(total, pagination.page, pagination.limit),
    )


@router.get("/categories", response_model=ApiResponse[list[StandardCategoryResponse]])
async def list_categories(
    service: StandardServiceDep,
    standard_code: str | None = Query(default=None),
    version_year: str | None = Query(default=None),
    is_latest: bool | None = Query(default=None),
):
    return ApiResponse(data=await service.list_categories(standard_code, version_year, is_latest))


# NOTE: static paths ("/bulk", "/categories") must be declared before "/{standard_id}" —
# otherwise FastAPI matches them as the path parameter instead.
@router.get("/{standard_id}", response_model=ApiResponse[StandardResponse], responses={**RESP_404})
async def get_standard(standard_id: str, service: StandardServiceDep):
    return ApiResponse(data=await service.get_standard(standard_id))


@router.patch("/{standard_id}", response_model=ApiResponse[StandardResponse], responses={**RESP_400, **RESP_404})
async def update_standard(standard_id: str, payload: UpdateStandardRequest, service: StandardServiceDep):
    return ApiResponse(data=await service.update_standard(standard_id, payload))


@router.delete("/{standard_id}", status_code=status.HTTP_204_NO_CONTENT, responses={**RESP_404})
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

## 9b. Assets & Fixtures — Postgres persistence

First SQL modules. UUID v4 primary keys.

**Assets** (`modules/assets/`) is a shared file catalog, not owned by fixtures. `relative_path` is the `AbstractFileStorage` key (unique). Other modules attach files by storing `assets.id`. No reverse collections on `Asset` (assets must not import fixtures).

HTTP (`/api/v1/assets`):

- `POST /` — multipart `file`. Saves via `LocalFileStorage` (`subfolder="assets"`), then inserts `Asset`. 201 `ApiResponse[AssetResponse]`.
- `GET /` — DB rows. `PaginationQuery` + optional `name` (case-insensitive substring on `original_filename` via `KeywordSpecification` / `SEARCHABLE_FIELDS = ["original_filename"]`). 200 `ApiResponse[list[AssetResponse]]` with pagination.
- `GET /{asset_id}` — **file stream** (`StreamingResponse`), not the JSON envelope. 404 `{detail: ...}` if the row or bytes are missing.

No DELETE/PATCH. `AssetResponse`: `id`, `relative_path`, `original_filename`, `mime_type`, `size_bytes`, `created_at`.

**Fixtures** (`modules/fixtures/`) FKs to assets: `ies_file_id` (required), `model_3d_file_id` (nullable), `image_file_id`. Parent→child **CASCADE**; asset FKs **RESTRICT**. Upload stays on `/assets`; fixtures only store UUIDs. Writes are one resource per request (`SQLRepository` commits per call — no nested create of fixture+variants in one body).

HTTP (`/api/v1/fixtures`):

- `POST /` / `GET /` / `GET /{id}` / `PATCH /{id}` / `DELETE /{id}` (204). List is `FixtureSummaryResponse` (no variants). Get-by-id is `FixtureResponse` via `get_with_variants`.
- List filters: `q` (`KeywordSpecification` on `manufacturer_name` + `name`), `application` (`ArrayContains`), `is_main_solution`.
- `POST/GET/PATCH/DELETE /{id}/variants/...` — duplicate `(fixture_id, name)` is 409; missing/mismatched parent is 404. GET is `VariantDetailResponse` via `get_with_fixture` (parent `FixtureSummaryResponse`, no nested variants). POST/PATCH stay `VariantResponse`.
- `POST/DELETE /{id}/variants/{vid}/images/...` — `{image_file_id}`; duplicate pair is 409.

Asset FKs are checked with `AssetRepository.get_by_id` before insert (404 `"Asset not found"`). DTO unique-list validators cover applications / protections (PG cannot CHECK `DISTINCT unnest`).

`fixture_applications` is **not** a child table: `fixtures.applications` is `TEXT[]` of `{interior, industrial}` (“both” = both values). Same for variant `mechanical_protections` / `electrical_protections`.

Repositories subclass `SQLRepository[Model, UUID]`. Default `_options()` `selectinload`s to-one `Asset` FKs (and variant images). Extra commands: `FixtureRepository.get_with_variants(id)` and `FixtureVariantRepository.get_with_fixture(id)` (fixture + `ies_file` only — not the sibling variants graph). List/find do not load those. Unique lookups use `get_one(FieldEquals(...))`. DI: `Depends(get_postgres_session)` in each `dependencies.py`.

Alembic: `alembic/env.py` reads `POSTGRES_DSN`, imports both model modules. Initial revision `0001_assets_fixtures`. Run `alembic upgrade head`. DSN must be `postgresql+asyncpg://...`.

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

`POST /standards/bulk` validates the batch (schema + `reject_duplicate_keys`) then returns **`202 Accepted`** with `ApiResponse` wrapping `{status: "accepted", item_count: N}` (`pagination` is `null`) and runs `create_many_standards` in a FastAPI `BackgroundTasks` job. The worker applies the same per-item insert/skip rules but **does not** report outcomes back — the HTTP response has already been sent.

> Ceiling: `BackgroundTasks` are in-process; a crash loses the job and there is no status endpoint. Upgrade to a real queue (or a job document) if bulk ingest must be durable.

This pattern (natural key as the DB id + a computed content fingerprint + a UUID v5 point id from immutable identity fields) generalizes to any future module ingesting externally-sourced, re-importable data. For modules where the DB should own identity, skip this — a normal auto-generated ID with a plain `create`/`409-if-exists` is enough.

---

## 11. Adding a New Module — Checklist

1. Create `modules/<name>/` with the six files: `models.py`, `dto.py`, `repository.py`, `service.py`, `controller.py`, `dependencies.py`.
2. **`models.py`**: define the entity — a Beanie `Document` (Mongo) or a `Mapped[...]` SQLAlchemy class (Postgres). Decide the ID strategy up front (auto-generated vs. natural key) — it determines whether you need Standards-style idempotency logic.
3. **`dto.py`**: `Create{X}Request`, `Update{X}Request` (all optional), `{X}Response`, plus bulk variants if needed. `extra="forbid"` + explicit `Field` constraints on everything. Derived fields (`content_hash`, `qdrant_point_id`, timestamps) and immutable identity fields stay off the request models they don't belong on.
4. **`repository.py`**: subclass `SQLRepository[Model, IdType]` or `MongoRepository[Model, IdType]`, set `model = ...`, add custom queries only if `find(spec)` / `count(spec)` / `get_one(spec)` genuinely can't express them (Standards `distinct_categories` is a `$group` — not a generic base-class method). SQL subclasses override `_options()` for `selectinload`.
5. **`service.py`**: business logic only — DTO↔entity mapping, idempotency/business rules, `HTTPException` for domain errors (404/409/etc). List methods return `(items, total_count)` from `find` + `count`. Define a `SEARCHABLE_FIELDS` allowlist here if the module needs keyword search.
6. **`controller.py`**: thin routes, `response_model=ApiResponse[...]` on every JSON success (list: `ApiResponse[list[{X}Response]]`). Wrap returns in `ApiResponse`; collection GET injects `Annotated[PaginationQuery, Depends()]` and sets `pagination=PaginationMeta.from_query(...)`. Bounded distinct lookups (`GET /standards/categories`) leave `pagination` null. DELETE stays 204 with no body. File download (assets `GET /{id}`) is `StreamingResponse`, not the envelope. Static paths (`/search`, `/bulk`, `/categories`) before `/{id}` paths.
7. **`dependencies.py`**: `get_<x>_repository` → `get_<x>_service` → `<X>ServiceDep`.
8. Register the router in `main.py` (when the module has HTTP). If Mongo: add the `Document` class to `init_beanie(document_models=[...])` in `db/mongo/client.py`. If Postgres: import the models in `alembic/env.py` and generate an Alembic migration.
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

    POSTGRES_DSN: str | None = None  # lazy-checked on first session / Alembic; tests boot without it

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
from app.db.postgres.session import dispose_postgres
from app.modules.standards.controller import router as standards_router
from app.modules.assets.controller import router as assets_router
from app.modules.fixtures.controller import router as fixtures_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_mongo()
    yield
    await close_mongo()
    await dispose_postgres()

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.include_router(standards_router, prefix="/api/v1")
app.include_router(assets_router, prefix="/api/v1")
app.include_router(fixtures_router, prefix="/api/v1")
```

Postgres tables are managed via **Alembic** (`alembic/` + `alembic.ini`) against `app.db.postgres.base.Base.metadata`. `env.py` must import every SQL module's `models` so autogenerate sees them. Mongo needs none — Beanie just needs every `Document` subclass listed in `init_beanie(document_models=[...])`.

---

## 13. Consistent Error Responses (also visible in Swagger)

```python
# shared/dto/error.py
from pydantic import BaseModel

class ErrorResponse(BaseModel):
    detail: str
```

The examples in Section 9 raise `HTTPException` directly, which FastAPI already turns into a `{"detail": "..."}` JSON body — consistent with `ErrorResponse` above, and **not** wrapped in `ApiResponse`. For per-route Swagger documentation of error shapes, add `responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}}` to route decorators as needed.

---

## 14. Local Dev Infra

No Docker in this repo. Run Mongo and Postgres however you already do.

Copy `.env.example` to `.env` and fill the names yourself. Names only — no sample hosts or passwords in `.env.example`:

```
MONGO_URI=
MONGO_DB_NAME=
POSTGRES_DSN=
LOCAL_STORAGE_PATH=
APP_NAME=
ENV=
```

`MONGO_URI` is required to boot. `POSTGRES_DSN` (`postgresql+asyncpg://...`) is required for Alembic and any assets/fixtures session; Settings keeps it optional so tests that import the app still boot. Fill it in `.env` yourself — do not put a sample value in `.env.example`.

---

## 15. Testing Strategy

**Hard rule: tests must not persist anything.** No Mongo, no Postgres, no files on disk, no TestClient lifespan that calls `init_mongo`. A fake in-memory repository (a dict behind `AbstractRepository`) is the only store. If a test would need a real database or `./uploads` to pass, the test is wrong. Beanie `Document.__init__` still needs collection settings, so `tests/conftest.py` assigns a dummy `Standard._document_settings` — that is not a database connection.

- **Service tests**: inject a `FakeStandardRepository`. Assert the happy path (computed `content_hash` / `qdrant_point_id` / timestamps, idempotent skip) and the error path (`HTTPException` 400/404/409). Nothing is written outside the fake.
  - Create payload has `_id` and **no** `content_hash` or `qdrant_point_id`; the entity the fake received has a computed hash, UUID v5 point id, and timestamps.
  - `create_standard` called twice with identical content → second call returns the existing record, fake `create` is not called again.
  - `create_standard` with the same `id` but different content → `409`.
  - `create_standard` with a new `id` but the same identity fields (same computed `qdrant_point_id`) → `409`.
  - PATCH of content recomputes the hash and leaves `qdrant_point_id` and identity fields untouched.
  - `reject_duplicate_keys` with a repeated `id` or a repeated computed `qdrant_point_id` in one payload → `400`.
  - `create_many_standards` (the worker) inserts only genuinely new items into the fake; same-id retries and taken point ids are skipped.
  - `list_categories`: two rows with the same metadata + table and different `ref_number` → one category; the same table number under a different `standard_code` → two categories, each carrying its `standard_metadata`.
- **Controller tests**: `httpx.AsyncClient` against an app that **does not** run the production lifespan, with `app.dependency_overrides[get_<x>_service] = lambda: FakeService()`. Assert status codes and response bodies (flow + errors). JSON 2xx bodies are `{success, data, pagination}`; collection GET fills `pagination`, other JSON routes have `pagination: null`. `HTTPException` 404/409 stay `{detail: ...}` (not the envelope). Pydantic 422s (unknown fields, `qdrant_point_id` on create, identity fields / `qdrant_point_id` / `content_hash` on PATCH, `page=0`) live here. `POST /bulk` returns **202** with `data.item_count` without waiting on inserts. `GET /categories` is **200** with `{success, data, pagination: null}` and is not captured by `/{standard_id}`. DELETE is **204** with no body. Assets: multipart POST 201; `GET /{id}` is raw file bytes (not the envelope); `?name=` is case-insensitive on `original_filename`. Fixtures: list has no `variants`; GET fixture by id includes the graph; GET variant includes `fixture` (summary, no variants); 409 on duplicate variant name; missing asset 404. Fakes never mkdir `./uploads`.
- **Helper tests**: `generate_qdrant_point_id` is stable for the same identity, differs for `6.1|6.1.3.1` vs `6.13|6.13.1`, and ignores `activity`. `PaginationQuery.skip` and `PaginationMeta.from_query` (including `total_pages=0` when `total_count=0`).
- **No repository/integration tests against a live engine.** Unique indexes and query plans are not the unit-test suite's job. Local Mongo is for running the app, not for pytest.

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
2. Copy `.env.example` to `.env` and fill `MONGO_URI`. Fill `POSTGRES_DSN` (`postgresql+asyncpg://...`) before `alembic upgrade head`.
3. Scaffold `core/`, `db/`, `storage/`, `shared/` as in Section 3.
4. Build `modules/standards/` from Section 9's code.
5. Wire `main.py` + `db/mongo/client.py` (Section 12), confirm Swagger UI at `/docs` shows accurate, strict schemas for every Standards route.
6. Add error handling (Section 13).
7. Add tests (Section 15) as you go, not after — in-memory fakes only, never against Mongo or `./uploads`.
8. For each new module going forward, follow Section 11's checklist.

---

## 18. Roadmap

- Auth (JWT or session-based) + `get_current_user` + per-route scopes.
- Mongo text index + `$text` search for `Standard.searchable_text` if `$regex` scanning becomes a bottleneck.
- `S3FileStorage` behind the same `AbstractFileStorage` interface.
- Structured logging + request ID middleware.
