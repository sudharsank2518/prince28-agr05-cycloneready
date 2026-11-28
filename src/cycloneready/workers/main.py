"""ARQ worker startup and configuration."""

import logging

from arq.connections import RedisSettings

from cycloneready.config import get_settings
from cycloneready.db.ingest_jobs import recover_unfinished_items
from cycloneready.db.session import make_engine, make_sessionmaker
from cycloneready.llm import create_llm_gateway
from cycloneready.llm.recorder import create_llm_recorder
from cycloneready.workers.ingest import ingest_document

logger = logging.getLogger("cycloneready.worker")


async def startup(ctx: dict) -> None:
    """Initialize database, LLM gateway, and recover unfinished items."""

    settings = get_settings()

    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)

    recorder = create_llm_recorder(sessionmaker)
    gateway = create_llm_gateway(settings, recorder=recorder)

    ctx["settings"] = settings
    ctx["engine"] = engine
    ctx["sessionmaker"] = sessionmaker
    ctx["gateway"] = gateway

    recovered = await recover_unfinished_items(sessionmaker, settings)

    logger.info("Worker started. Recovered %s unfinished items.", recovered)


async def shutdown(ctx: dict) -> None:
    """Close worker database connections."""

    engine = ctx.get("engine")

    if engine is not None:
        await engine.dispose()

    logger.info("Worker shut down.")


class WorkerSettings:
    """ARQ worker configuration."""

    functions = [ingest_document]
    on_startup = startup
    on_shutdown = shutdown

    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)

    max_jobs = get_settings().ingest_concurrency
    job_timeout = get_settings().ingest_job_timeout
    max_tries = get_settings().ingest_max_tries
