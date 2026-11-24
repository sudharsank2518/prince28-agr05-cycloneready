"""Parse downloaded corpus files and store their pages in PostgreSQL."""

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cycloneready.config import get_settings  # noqa: E402
from cycloneready.db.session import make_engine, make_sessionmaker  # noqa: E402
from cycloneready.ingest.parse import ParseError, parse_file  # noqa: E402
from cycloneready.ingest.store import (  # noqa: E402
    failed_paths,
    parsed_ids,
    save_document,
    save_failure,
)

MANIFEST = ROOT / "data" / "manifest.jsonl"


def read_manifest() -> list[dict]:
    """Read the manifest and keep the latest entry for each file URL."""
    latest = {}

    if not MANIFEST.exists():
        print("Manifest not found. No corpus files are available for parsing.")
        return []

    with MANIFEST.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                print("Skipping invalid manifest line.")
                continue

            url = record.get("url")
            if url:
                latest[url] = record

    return list(latest.values())


def file_sha256(path: Path) -> str:
    """Calculate a file's SHA-256 checksum."""
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


async def process_corpus(limit: int | None, retry_failed: bool) -> None:
    records = read_manifest()

    records = [
        record
        for record in records
        if record.get("status") in {"downloaded", "not_modified"} and record.get("file_path")
    ]

    if limit is not None:
        records = records[:limit]

    settings = get_settings()
    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)

    processed = 0
    failed = 0
    skipped = 0

    try:
        async with sessionmaker() as session:
            existing_ids = await parsed_ids(session)
            existing_failures = await failed_paths(session)

            for record in records:
                path = ROOT / record["file_path"]

                if not path.is_file():
                    print(f"Missing file: {path}")
                    skipped += 1
                    continue

                relative_path = str(path.relative_to(ROOT))

                if relative_path in existing_failures and not retry_failed:
                    print(f"Already failed; skipping: {relative_path}")
                    skipped += 1
                    continue

                sha256 = record.get("sha256") or file_sha256(path)
                external_id = f"f-{sha256[:20]}"

                if external_id in existing_ids:
                    print(f"Already parsed; skipping: {relative_path}")
                    skipped += 1
                    continue

                try:
                    parsed = parse_file(path)

                    await save_document(
                        session=session,
                        path=relative_path,
                        sha256=sha256,
                        source_url=record.get("url"),
                        licence=record.get("licence"),
                        parsed=parsed,
                    )

                    await session.commit()
                    existing_ids.add(external_id)
                    existing_failures.discard(relative_path)
                    processed += 1

                    print(f"Parsed: {relative_path}")

                except ParseError as error:
                    await save_failure(
                        session=session,
                        path=relative_path,
                        sha256=sha256,
                        source_url=record.get("url"),
                        reason=error.reason,
                        detail=error.detail,
                    )
                    await session.commit()
                    failed += 1

                    print(f"Failed: {relative_path} ({error.reason})")

                except Exception as error:
                    await session.rollback()
                    failed += 1
                    print(f"Unexpected error: {relative_path}: {error}")

    finally:
        await engine.dispose()

    print("\nParsing summary")
    print(f"Processed: {processed}")
    print(f"Failed:    {failed}")
    print(f"Skipped:   {skipped}")
    print(f"Total:     {len(records)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse downloaded corpus files into the database.")
    parser.add_argument("--limit", type=int, help="Maximum number of files to parse.")
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry files that previously failed parsing.",
    )

    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    asyncio.run(process_corpus(args.limit, args.retry_failed))


if __name__ == "__main__":
    main()
