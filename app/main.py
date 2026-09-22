from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.db.mongo.client import close_mongo, init_mongo
from app.db.postgres.session import dispose_postgres
from app.modules.assets.controller import router as assets_router
from app.modules.fixtures.controller import router as fixtures_router
from app.modules.standards.controller import router as standards_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_mongo()
    yield
    await close_mongo()
    await dispose_postgres()


setup_logging("DEBUG" if settings.ENV == "local" else "INFO")

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

origins = [
    "http://localhost:4200"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,           # Allows requests from specific domains
    allow_credentials=True,          # Allows cookies and authorization headers
    allow_methods=["*"],             # Allows all standard HTTP methods (GET, POST, etc.)
    allow_headers=["*"],             # Allows all headers
)

register_exception_handlers(app)
app.include_router(standards_router, prefix="/api/v1")
app.include_router(assets_router, prefix="/api/v1")
app.include_router(fixtures_router, prefix="/api/v1")
