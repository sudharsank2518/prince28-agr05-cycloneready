"""App factory: build a fully wired FastAPI app from settings."""

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from cycloneready.api.errors import register_error_handlers
from cycloneready.api.middleware import request_context
from cycloneready.api.routes import chat, cyclones, documents, health, ingest, llm
from cycloneready.config import Settings, get_settings
from cycloneready.db.session import make_engine, make_sessionmaker
from cycloneready.llm import create_llm_gateway
from cycloneready.llm.recorder import create_llm_recorder
from cycloneready.logging_setup import setup_logging

logger = logging.getLogger("cycloneready")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the CycloneReady application."""

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

    # Store application dependencies.
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker

    # Configure LLM usage recording.
    app.state.llm_recorder = create_llm_recorder(sessionmaker)

    # Create the LLM gateway.
    app.state.llm_gateway = create_llm_gateway(
        settings,
        recorder=app.state.llm_recorder,
    )

    # Load the system prompt once during application creation.
    prompt_path = settings.prompts_dir / "chat_system_v1.md"
    app.state.system_prompt = prompt_path.read_text(encoding="utf-8")
    app.state.llm_gateway.system_prompt = app.state.system_prompt

    # Register middleware and error handlers.
    app.middleware("http")(request_context)
    register_error_handlers(app)

    # Register version 1 API routes.
    v1 = APIRouter(prefix="/v1")
    v1.include_router(documents.router)
    v1.include_router(cyclones.router)
    v1.include_router(chat.router)
    v1.include_router(llm.router)
    v1.include_router(ingest.router)

    app.include_router(health.router)
    app.include_router(v1)

    return app
