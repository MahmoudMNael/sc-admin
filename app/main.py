from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.db.mongo.client import close_mongo, init_mongo
from app.modules.standards.controller import router as standards_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_mongo()
    yield
    await close_mongo()
    # once the first Postgres module exists: import the engine and `await engine.dispose()` here too


setup_logging("DEBUG" if settings.ENV == "local" else "INFO")

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
register_exception_handlers(app)
app.include_router(standards_router, prefix="/api/v1")
