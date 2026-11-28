"""Redis queue helpers for background document ingestion."""

from arq import create_pool
from arq.connections import RedisSettings

from cycloneready.config import get_settings


async def get_redis_pool():
    """Create a Redis connection pool using application settings."""
    settings = get_settings()
    return await create_pool(RedisSettings.from_dsn(settings.redis_url))


async def enqueue_ingest_item(pool, item_id: int):
    """Add one ingestion item to ARQ, using a stable ID to avoid duplicates."""
    return await pool.enqueue_job(
        "ingest_document",
        item_id,
        _job_id=f"ingest:{item_id}",
    )
