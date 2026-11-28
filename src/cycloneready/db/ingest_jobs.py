"""Database helpers for background ingestion jobs."""

from arq.constants import job_key_prefix, result_key_prefix
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from cycloneready.config import Settings
from cycloneready.db.models import IngestItem
from cycloneready.workers.queue import enqueue_ingest_item, get_redis_pool


async def recover_unfinished_items(
    sessionmaker: async_sessionmaker,
    settings: Settings,
) -> int:
    """Requeue unfinished items after a worker restart."""

    async with sessionmaker() as session:
        # Items that exhausted their retry allowance become dead letters.
        await session.execute(
            update(IngestItem)
            .where(
                IngestItem.status.in_(["processing", "queued"]),
                IngestItem.attempts >= settings.ingest_max_tries,
            )
            .values(status="dead")
        )

        # A worker may have been killed while processing an item.
        await session.execute(
            update(IngestItem).where(IngestItem.status == "processing").values(status="queued")
        )

        await session.commit()

        result = await session.execute(
            select(IngestItem.id).where(
                IngestItem.status == "queued",
                IngestItem.attempts < settings.ingest_max_tries,
            )
        )
        item_ids = list(result.scalars().all())

    if not item_ids:
        return 0

    pool = await get_redis_pool()
    enqueued_count = 0

    try:
        for item_id in item_ids:
            job_id = f"ingest:{item_id}"
            job_key = f"{job_key_prefix}{job_id}"
            result_key = f"{result_key_prefix}{job_id}"

            # Remove an old result only if no job currently exists.
            if not await pool.exists(job_key):
                await pool.delete(result_key)

            # Existing active jobs are left untouched.
            job = await enqueue_ingest_item(pool, item_id)

            if job is not None:
                enqueued_count += 1

    finally:
        await pool.aclose()

    return enqueued_count
