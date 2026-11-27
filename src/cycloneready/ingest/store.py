"""Store parsed documents, pages, cyclone observations, and failures."""

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from cycloneready.db.models import (
    CycloneObservation,
    Document,
    Page,
    ParseFailure,
)
from cycloneready.ingest.parse import ParsedDoc


def document_id(sha256: str) -> str:
    """Create a stable external ID from a file's SHA256 hash."""
    return f"f-{sha256[:20]}"


async def parsed_ids(session: AsyncSession) -> set[str]:
    """Return external IDs of documents that have already been parsed."""
    result = await session.execute(
        select(Document.external_id).where(Document.doc_type != "record")
    )
    return set(result.scalars().all())


async def failed_paths(session: AsyncSession) -> set[str]:
    """Return paths already recorded in the failure table."""
    result = await session.execute(select(ParseFailure.path))
    return set(result.scalars().all())


async def save_document(
    session: AsyncSession,
    path: str,
    sha256: str,
    source_url: str | None,
    licence: str | None,
    parsed: ParsedDoc,
) -> Document:
    """Save a parsed document, its pages, and its cyclone observations."""

    external_id = document_id(sha256)

    document = await session.scalar(select(Document).where(Document.external_id == external_id))

    if document is None:
        document = Document(
            external_id=external_id,
            title=parsed.title,
            source_url=source_url,
            licence=licence,
            doc_type=parsed.kind,
            sha256=sha256,
            metadata_={
                "parser": parsed.parser,
                "pages": len(parsed.pages),
                "tables": sum(page.tables for page in parsed.pages),
                "observations": len(parsed.observations),
                "ocr_candidate_pages": parsed.ocr_candidate_pages,
                "path": path,
            },
        )

        session.add(document)
        await session.flush()

    else:
        document.title = parsed.title
        document.source_url = source_url
        document.licence = licence
        document.doc_type = parsed.kind
        document.sha256 = sha256

        document.metadata_ = {
            **(document.metadata_ or {}),
            "parser": parsed.parser,
            "pages": len(parsed.pages),
            "tables": sum(page.tables for page in parsed.pages),
            "observations": len(parsed.observations),
            "path": path,
        }

        # Remove old pages before inserting updated pages.
        await session.execute(delete(Page).where(Page.document_id == document.id))

        # Remove old cyclone observations before reprocessing.
        await session.execute(
            delete(CycloneObservation).where(CycloneObservation.document_id == document.id)
        )

    # Save parsed document pages.
    for page in parsed.pages:
        session.add(
            Page(
                document_id=document.id,
                page_no=page.page_no,
                text=page.text,
                headings=page.headings,
            )
        )

    # Save cyclone observations in batches.
    if parsed.observations:
        batch_size = 1000
        total = len(parsed.observations)

        for start in range(0, total, batch_size):
            batch = parsed.observations[start : start + batch_size]

            observation_rows = [
                {
                    "document_id": document.id,
                    "storm_id": observation.storm_id,
                    "storm_number": observation.storm_number,
                    "basin": observation.basin,
                    "subbasin": observation.subbasin,
                    "observed_at": observation.observed_at,
                    "nature": observation.nature,
                    "latitude": observation.latitude,
                    "longitude": observation.longitude,
                    "wind_speed_kt": observation.wind_speed_kt,
                    "pressure_mb": observation.pressure_mb,
                }
                for observation in batch
            ]

            await session.execute(
                insert(CycloneObservation),
                observation_rows,
            )

            inserted = min(start + batch_size, total)

            print(f"Inserted observations: {inserted}/{total}")

    # Remove the previous failure record after successful parsing.
    await session.execute(delete(ParseFailure).where(ParseFailure.path == path))

    await session.flush()

    return document


async def save_failure(
    session: AsyncSession,
    path: str,
    sha256: str,
    source_url: str | None,
    reason: str,
    detail: str = "",
) -> None:
    """Insert a failure or update its details and increment its attempts."""

    statement = insert(ParseFailure).values(
        path=path,
        sha256=sha256,
        source_url=source_url,
        reason=reason,
        detail=detail,
        attempts=1,
    )

    statement = statement.on_conflict_do_update(
        index_elements=[ParseFailure.path],
        set_={
            "sha256": statement.excluded.sha256,
            "source_url": statement.excluded.source_url,
            "reason": statement.excluded.reason,
            "detail": statement.excluded.detail,
            "attempts": ParseFailure.attempts + 1,
        },
    )

    await session.execute(statement)
    await session.flush()
