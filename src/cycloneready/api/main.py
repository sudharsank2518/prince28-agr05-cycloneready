"""App factory: build a fully wired FastAPI app from settings."""

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from cycloneready.api.errors import register_error_handlers
from cycloneready.api.middleware import request_context
from cycloneready.api.routes import cyclones, documents, health
from cycloneready.config import Settings, get_settings
from cycloneready.db.session import make_engine, make_sessionmaker
from cycloneready.logging_setup import setup_logging

logger = logging.getLogger("cycloneready")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker

    app.middleware("http")(request_context)
    register_error_handlers(app)

    v1 = APIRouter(prefix="/v1")
    v1.include_router(documents.router)
    v1.include_router(cyclones.router)

    app.include_router(health.router)
    app.include_router(v1)

    return app
