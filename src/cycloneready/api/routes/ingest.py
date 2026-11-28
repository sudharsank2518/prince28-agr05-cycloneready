"""API endpoints for background document ingestion."""

import json
import secrets
import uuid
from pathlib import Path
from typing import Annotated, Any

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from cycloneready.api.deps import DbSessionDep, SettingsDep
from cycloneready.db.models import IngestItem, IngestJob
from cycloneready.workers.queue import (
    enqueue_ingest_item,
    get_redis_pool,
)

router = APIRouter(prefix="/ingest", tags=["ingestion"])


async def require_admin(
    settings: SettingsDep,
    token: Annotated[str, Header(alias="X-Admin-Token")] = "",
) -> None:
    """Require a valid admin token."""

    if not settings.admin_token or not secrets.compare_digest(
        token,
        settings.admin_token,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token.",
        )


async def get_redis_dependency():
    """Provide a Redis pool and close it after the request."""

    pool = await get_redis_pool()

    try:
        yield pool
    finally:
        await pool.aclose()


RedisDep = Annotated[ArqRedis, Depends(get_redis_dependency)]


def load_latest_manifest(manifest_file: Path) -> list[dict[str, Any]]:
    """Read the manifest and return the latest record for each URL."""

    latest: dict[str, dict[str, Any]] = {}

    if not manifest_file.exists():
        return []

    with manifest_file.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            url = record.get("url")

            if url:
                latest[url] = record

    return [
        record
        for record in latest.values()
        if record.get("status") in {"downloaded", "not_modified"}
    ]


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_ingest_job(
    session: DbSessionDep,
    settings: SettingsDep,
    pool: RedisDep,
    _: Annotated[None, Depends(require_admin)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> dict:
    """Create an ingestion job and enqueue its documents."""

    records = load_latest_manifest(settings.manifest_file)[:limit]

    if not records:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No successfully downloaded documents found in the manifest.",
        )

    job_id = uuid.uuid4().hex

    job = IngestJob(
        id=job_id,
        requested=len(records),
        items=[
            IngestItem(
                record=record,
                status="queued",
            )
            for record in records
        ],
    )

    session.add(job)
    await session.commit()

    item_ids = [item.id for item in job.items]

    queued = 0

    for item_id in item_ids:
        result = await enqueue_ingest_item(pool, item_id)

        if result is not None:
            queued += 1

    return {
        "job_id": job_id,
        "requested": len(records),
        "queued": queued,
        "status": "queued",
    }


@router.get("/dead-letter")
async def list_dead_letter_items(
    session: DbSessionDep,
    _: Annotated[None, Depends(require_admin)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict:
    """List documents that exhausted their retry allowance."""

    result = await session.execute(
        select(IngestItem)
        .where(IngestItem.status == "dead")
        .order_by(IngestItem.updated_at.desc())
        .limit(limit)
    )

    items = result.scalars().all()

    return {
        "total": len(items),
        "items": [
            {
                "id": item.id,
                "job_id": item.job_id,
                "title": item.record.get("title"),
                "url": item.record.get("url"),
                "attempts": item.attempts,
                "error": item.error,
                "updated_at": item.updated_at,
            }
            for item in items
        ],
    }


@router.get("/stats")
async def get_ingest_stats(
    session: DbSessionDep,
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    """Return ingestion counts and the age of the oldest queued item."""

    result = await session.execute(
        select(IngestItem)
        .where(IngestItem.status == "queued")
        .options(selectinload(IngestItem.job))
        .order_by(IngestItem.updated_at.asc())
    )

    queued_items = result.scalars().all()

    counts = {
        "queued": 0,
        "processing": 0,
        "completed": 0,
        "dead": 0,
    }

    for status_name in counts:
        result = await session.execute(select(IngestItem).where(IngestItem.status == status_name))
        counts[status_name] = len(result.scalars().all())

    oldest_queued_age_seconds = None

    if queued_items:
        from datetime import UTC, datetime

        oldest_created_at = min(item.job.created_at for item in queued_items)

        if oldest_created_at.tzinfo is None:
            oldest_created_at = oldest_created_at.replace(tzinfo=UTC)

        oldest_queued_age_seconds = max(
            0,
            int((datetime.now(UTC) - oldest_created_at).total_seconds()),
        )

    return {
        "counts": counts,
        "oldest_queued_age_seconds": oldest_queued_age_seconds,
    }


@router.get("/{job_id}")
async def get_ingest_job(
    job_id: str,
    session: DbSessionDep,
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    """Get ingestion job progress and item details."""

    result = await session.execute(
        select(IngestJob).where(IngestJob.id == job_id).options(selectinload(IngestJob.items))
    )

    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion job not found.",
        )

    counts = {
        "queued": 0,
        "processing": 0,
        "completed": 0,
        "dead": 0,
    }

    for item in job.items:
        if item.status in counts:
            counts[item.status] += 1

    return {
        "job_id": job.id,
        "requested": job.requested,
        "created_at": job.created_at,
        "counts": counts,
        "items": [
            {
                "id": item.id,
                "title": item.record.get("title"),
                "status": item.status,
                "attempts": item.attempts,
                "pages": item.pages,
                "error": item.error,
            }
            for item in job.items
        ],
    }
