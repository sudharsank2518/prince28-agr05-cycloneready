"""ARQ worker for downloading, parsing, and storing documents."""

import asyncio
from pathlib import Path
from typing import Any

from arq import Retry
from sqlalchemy.ext.asyncio import async_sessionmaker

from cycloneready.config import Settings
from cycloneready.db.models import IngestItem
from cycloneready.ingest.fetch import Fetcher
from cycloneready.ingest.parse import parse_file
from cycloneready.ingest.store import save_document
from cycloneready.llm.extract import (
    chunk_pages,
    extract_metadata,
    merge_metadata,
)


class PermanentIngestError(Exception):
    """An ingestion error that should not be retried."""


async def ingest_document(ctx: dict[str, Any], item_id: int) -> None:
    """Process one queued document."""

    settings: Settings = ctx["settings"]
    sessionmaker: async_sessionmaker = ctx["sessionmaker"]

    # Mark the item as processing and increment its attempt count.
    async with sessionmaker() as session:
        item = await session.get(IngestItem, item_id)

        if item is None or item.status in {"completed", "dead"}:
            return

        item.status = "processing"
        item.attempts += 1
        item.error = ""

        record = dict(item.record)
        await session.commit()

    try:
        # Download the source or reuse its existing downloaded file.
        async with Fetcher(
            manifest_path=settings.manifest_file,
            delay=60.0 / settings.ingest_rpm,
            max_concurrency=1,
        ) as fetcher:
            result = await fetcher.fetch_one(record)
            manifest_record = fetcher.latest.get(record["url"], {})

        if result["result"] == "blocked":
            raise PermanentIngestError("Source is blocked by robots.txt.")

        if result["result"] == "failed":
            raise RuntimeError(result.get("reason", "Source download failed."))

        file_path = manifest_record.get("file_path")
        sha256 = manifest_record.get("sha256")

        if not file_path or not sha256:
            raise RuntimeError("Downloaded file is missing its path or SHA256.")

        path = Path(file_path)

        if not path.is_file():
            raise RuntimeError(f"Downloaded file does not exist: {path}")

        # Parse the downloaded document.
        parsed = parse_file(path)

        # Extract structured metadata from the parsed pages.
        page_texts = [page.text for page in parsed.pages]
        chunks = chunk_pages(page_texts)

        metadata = None

        if chunks:
            prompt_path = settings.prompts_dir / "extract_v1.md"
            prompt = prompt_path.read_text(encoding="utf-8")

            metadata_results = []

            for chunk in chunks:
                extracted, _ = await extract_metadata(
                    ctx["gateway"],
                    prompt,
                    "v1",
                    chunk,
                )
                metadata_results.append(extracted)

            metadata = merge_metadata(metadata_results)

        # Save the document, pages, metadata, and completed queue status.
        async with sessionmaker() as session, session.begin():
            document = await save_document(
                session=session,
                path=str(path),
                sha256=sha256,
                source_url=record.get("url"),
                licence=record.get("licence"),
                parsed=parsed,
            )

            if metadata is not None:
                document.metadata_ = {
                    **(document.metadata_ or {}),
                    **metadata.model_dump(),
                }

            item = await session.get(IngestItem, item_id)

            if item is not None:
                item.status = "completed"
                item.pages = len(parsed.pages)
                item.error = ""

        print(f"Ingestion completed: item={item_id}, pages={len(parsed.pages)}")

    except asyncio.CancelledError:
        # If ARQ cancels a job, return the item to the queue.
        async with sessionmaker() as session, session.begin():
            item = await session.get(IngestItem, item_id)

            if item is not None and item.status == "processing":
                item.status = "queued"
                item.error = "Worker job timed out or was cancelled."

        print(f"Ingestion cancelled: item={item_id}; returned to queue.")
        raise

    except PermanentIngestError as exc:
        async with sessionmaker() as session, session.begin():
            item = await session.get(IngestItem, item_id)

            if item is not None:
                item.status = "dead"
                item.error = str(exc)[:2000]

        print(f"Ingestion permanently failed: item={item_id}: {exc}")

    except Exception as exc:
        # Daily quota exhaustion is not a normal retryable failure.
        # Keep the item queued and restore the attempt consumed by this run.
        if getattr(exc, "quota_exhausted", False):
            async with sessionmaker() as session, session.begin():
                item = await session.get(IngestItem, item_id)

                if item is not None:
                    item.status = "queued"
                    item.attempts = max(0, item.attempts - 1)
                    item.error = str(exc)[:2000]

            print(
                f"Provider daily quota exhausted: item={item_id}; "
                "returned to queue without consuming an attempt."
            )
            return

        async with sessionmaker() as session, session.begin():
            item = await session.get(IngestItem, item_id)

            if item is None:
                raise

            item.error = str(exc)[:2000]

            if item.attempts >= settings.ingest_max_tries:
                item.status = "dead"
                print(f"Ingestion moved to dead letter: item={item_id}: {exc}")
                return

            item.status = "queued"

        # ARQ retries the job after a short delay.
        delay = min(300, 60 * (2 ** (item.attempts - 1)))
        raise Retry(defer=delay) from exc
