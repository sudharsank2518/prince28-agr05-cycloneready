"""Tests for recovering unfinished ingestion jobs."""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cycloneready.config import Settings
from cycloneready.db.ingest_jobs import recover_unfinished_items
from cycloneready.db.models import Base, IngestItem, IngestJob


@pytest.fixture
def recovery_db(tmp_path):
    """Create an isolated temporary database for recovery tests."""

    database_path = tmp_path / "recovery.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    engine = create_async_engine(database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def create_schema():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_schema())

    yield sessionmaker

    asyncio.run(engine.dispose())


def test_recovery_requeues_interrupted_items_and_marks_exhausted_dead(recovery_db, monkeypatch):
    """Interrupted items are requeued; exhausted items become dead."""

    class FakeRedisPool:
        async def exists(self, key):
            return False

        async def delete(self, key):
            return 1

        async def aclose(self):
            pass

    fake_pool = FakeRedisPool()
    enqueued_ids = []

    async def fake_get_redis_pool():
        return fake_pool

    async def fake_enqueue(pool, item_id):
        enqueued_ids.append(item_id)
        return object()

    monkeypatch.setattr(
        "cycloneready.db.ingest_jobs.get_redis_pool",
        fake_get_redis_pool,
    )
    monkeypatch.setattr(
        "cycloneready.db.ingest_jobs.enqueue_ingest_item",
        fake_enqueue,
    )

    async def prepare_and_check():
        async with recovery_db() as session:
            job = IngestJob(
                id="recovery-test",
                requested=3,
                items=[
                    IngestItem(
                        record={"id": "001"},
                        status="processing",
                        attempts=1,
                    ),
                    IngestItem(
                        record={"id": "002"},
                        status="queued",
                        attempts=0,
                    ),
                    IngestItem(
                        record={"id": "003"},
                        status="processing",
                        attempts=3,
                    ),
                ],
            )
            session.add(job)
            await session.commit()

            result = await session.execute(select(IngestItem).order_by(IngestItem.id))
            items = list(result.scalars().all())
            item_ids = [item.id for item in items]

        settings = Settings(
            app_env="ci",
            database_url="sqlite+aiosqlite://",
            ingest_max_tries=3,
        )

        recovered = await recover_unfinished_items(recovery_db, settings)

        async with recovery_db() as session:
            result = await session.execute(select(IngestItem).order_by(IngestItem.id))
            items = list(result.scalars().all())

        return recovered, item_ids, items

    recovered, item_ids, items = asyncio.run(prepare_and_check())

    assert recovered == 2
    assert enqueued_ids == item_ids[:2]
    assert [item.status for item in items] == [
        "queued",
        "queued",
        "dead",
    ]


def test_recovery_returns_zero_when_no_items_are_eligible(recovery_db, monkeypatch):
    """Recovery does not connect to Redis when there is no work."""

    async def unexpected_redis_connection():
        pytest.fail("Redis should not be accessed when there are no items")

    monkeypatch.setattr(
        "cycloneready.db.ingest_jobs.get_redis_pool",
        unexpected_redis_connection,
    )

    settings = Settings(
        app_env="ci",
        database_url="sqlite+aiosqlite://",
        ingest_max_tries=3,
    )

    recovered = asyncio.run(recover_unfinished_items(recovery_db, settings))

    assert recovered == 0
