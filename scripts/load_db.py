"""Load sample records into PostgreSQL using SHA-256 fingerprints."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from sqlalchemy import delete, select

from cycloneready.config import get_settings
from cycloneready.db.models import Document
from cycloneready.db.session import make_engine, make_sessionmaker


def fingerprint(record: dict) -> str:
    content = json.dumps(record, sort_keys=True).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load sample records into PostgreSQL")
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Delete database documents absent from the input file",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    settings = get_settings()
    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)

    inserted = 0
    updated = 0
    unchanged = 0
    deleted = 0

    try:
        records = json.loads(Path(settings.data_file).read_text(encoding="utf-8"))

        # Collect IDs present in the input file.
        input_ids = {str(record["id"]) for record in records}

        async with sessionmaker() as session:
            for record in records:
                record_hash = fingerprint(record)

                result = await session.execute(
                    select(Document).where(Document.external_id == str(record["id"]))
                )
                document = result.scalar_one_or_none()

                # Store the key field in the typed column.
                document_value = record.get("document")

                # Keep other fields in JSONB metadata.
                metadata = {
                    key: value
                    for key, value in record.items()
                    if key
                    not in {
                        "id",
                        "title",
                        "document",
                        "source_url",
                        "licence",
                        "doc_type",
                        "published_on",
                    }
                }

                if document is None:
                    document = Document(
                        external_id=str(record["id"]),
                        title=record.get("title", document_value or ""),
                        document=document_value,
                        source_url=record.get("source_url"),
                        licence=record.get("licence"),
                        doc_type=record.get("doc_type", "record"),
                        published_on=record.get("published_on"),
                        metadata_=metadata,
                        sha256=record_hash,
                    )
                    session.add(document)
                    inserted += 1

                elif document.sha256 != record_hash:
                    document.title = record.get("title", document_value or "")
                    document.document = document_value
                    document.source_url = record.get("source_url")
                    document.licence = record.get("licence")
                    document.doc_type = record.get("doc_type", "record")
                    document.published_on = record.get("published_on")
                    document.metadata_ = metadata
                    document.sha256 = record_hash
                    updated += 1

                else:
                    unchanged += 1

            # Delete records not present in the input file, only with --prune.
            if args.prune:
                result = await session.execute(
                    delete(Document).where(Document.external_id.notin_(input_ids))
                )
                deleted = result.rowcount or 0

            await session.commit()

        print(
            f"records={len(records)} "
            f"inserted={inserted} "
            f"updated={updated} "
            f"unchanged={unchanged} "
            f"deleted={deleted}"
        )

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
