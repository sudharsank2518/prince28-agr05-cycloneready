"""Parse downloaded corpus files and store their pages in PostgreSQL."""

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

from sqlalchemy.exc import DBAPIError

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


def is_transient_connection_error(error: DBAPIError) -> bool:
    """Check whether a database error looks like a temporary connection failure."""
    if error.connection_invalidated:
        return True

    message = str(error).lower()

    connection_errors = (
        "connection was closed",
        "connection closed",
        "connection reset",
        "connection terminated",
        "server closed the connection",
        "connection is closed",
    )

    return any(text in message for text in connection_errors)


def resolve_selected_paths(paths: list[str]) -> set[Path]:
    """Resolve selected file paths relative to the project root."""
    selected = set()

    for value in paths:
        path = Path(value)

        if not path.is_absolute():
            path = ROOT / path

        selected.add(path.resolve())

    return selected


async def process_corpus(
    limit: int | None,
    retry_failed: bool,
    reprocess: bool,
    paths: list[str] | None = None,
) -> None:
    records = read_manifest()

    records = [
        record
        for record in records
        if record.get("status") in {"downloaded", "not_modified"} and record.get("file_path")
    ]

    # Select only explicitly requested files when --path is supplied.
    if paths:
        selected_paths = resolve_selected_paths(paths)

        records = [
            record for record in records if (ROOT / record["file_path"]).resolve() in selected_paths
        ]

        found_paths = {(ROOT / record["file_path"]).resolve() for record in records}

        missing_paths = selected_paths - found_paths

        if missing_paths:
            missing = ", ".join(str(path) for path in sorted(missing_paths))
            raise ValueError(
                f"These selected files were not found as eligible manifest entries: {missing}"
            )

    if limit is not None:
        records = records[:limit]

    print(f"Files selected for parsing: {len(records)}")

    settings = get_settings()
    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)

    processed = 0
    failed = 0
    skipped = 0
    total_observations = 0

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

            if external_id in existing_ids and not reprocess:
                print(f"Already parsed; skipping: {relative_path}")
                skipped += 1
                continue

            # Parse the file once. Parsing errors are not retried.
            try:
                parsed = parse_file(path)
            except ParseError as error:
                async with sessionmaker() as session:
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
                continue

            # Retry database connection failures using a fresh session.
            max_attempts = 3
            saved = False

            for attempt in range(1, max_attempts + 1):
                try:
                    async with sessionmaker() as session:
                        await save_document(
                            session=session,
                            path=relative_path,
                            sha256=sha256,
                            source_url=record.get("url"),
                            licence=record.get("licence"),
                            parsed=parsed,
                        )

                        await session.commit()

                    saved = True
                    break

                except DBAPIError as error:
                    if is_transient_connection_error(error) and attempt < max_attempts:
                        delay = 2**attempt
                        print(
                            f"Temporary database connection error for "
                            f"{relative_path}. "
                            f"Retrying ({attempt + 1}/{max_attempts}) "
                            f"in {delay} seconds..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        print(
                            f"Database error for {relative_path} "
                            f"(attempt {attempt}/{max_attempts}): {error}"
                        )
                        break

                except Exception as error:
                    print(f"Unexpected error: {relative_path}: {error}")
                    break

            if saved:
                existing_ids.add(external_id)
                existing_failures.discard(relative_path)

                processed += 1
                observation_count = len(parsed.observations)
                total_observations += observation_count

                print(f"Parsed: {relative_path} ({observation_count} cyclone observations)")
            else:
                failed += 1

    finally:
        await engine.dispose()

    print("\nParsing summary")
    print(f"Processed:            {processed}")
    print(f"Cyclone observations: {total_observations}")
    print(f"Failed:               {failed}")
    print(f"Skipped:              {skipped}")
    print(f"Total:                {len(records)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse downloaded corpus files into the database.")

    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of files to parse.",
    )

    parser.add_argument(
        "--path",
        action="append",
        help="Specific file path to parse. Can be supplied multiple times.",
    )

    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry files that previously failed parsing.",
    )

    parser.add_argument(
        "--reprocess",
        action="store_true",
        help="Reprocess files even if they were already parsed.",
    )

    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    asyncio.run(
        process_corpus(
            limit=args.limit,
            retry_failed=args.retry_failed,
            reprocess=args.reprocess,
            paths=args.path,
        )
    )


if __name__ == "__main__":
    main()
