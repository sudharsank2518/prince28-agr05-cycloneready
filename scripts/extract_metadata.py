"""Extract structured metadata from parsed PDF documents, with resumable progress."""

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cycloneready.config import get_settings  # noqa: E402
from cycloneready.db.models import Document, Page  # noqa: E402
from cycloneready.db.session import make_engine, make_sessionmaker  # noqa: E402
from cycloneready.llm import create_llm_gateway  # noqa: E402
from cycloneready.llm.doc_meta import DocMeta  # noqa: E402
from cycloneready.llm.extract import (  # noqa: E402
    chunk_pages,
    extract_metadata,
    merge_metadata,
)
from cycloneready.llm.prompts import list_versions, load_prompt  # noqa: E402
from cycloneready.llm.recorder import create_llm_recorder  # noqa: E402


def file_sha256(path: Path) -> str:
    """Calculate a file's SHA-256 checksum."""
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def resolve_selected_external_ids(paths: list[str]) -> set[str]:
    """Resolve selected PDF paths to their document external IDs."""
    external_ids = set()

    for value in paths:
        path = Path(value)

        if not path.is_absolute():
            path = ROOT / path

        path = path.resolve()

        if not path.is_file():
            raise FileNotFoundError(f"Selected PDF does not exist: {path}")

        sha256 = file_sha256(path)
        external_ids.add(f"f-{sha256[:20]}")

    return external_ids


def should_skip(status: str | None, retry_failed: bool, reprocess: bool) -> bool:
    """Determine whether a document should be skipped."""
    if reprocess:
        return False

    return status == "completed" or (status == "failed" and not retry_failed)


def create_fingerprints(prompt: str, chunks: list[str]) -> dict[str, str]:
    """Create hashes to detect changes in prompts and document content."""
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    content_hash = hashlib.sha256(
        json.dumps(
            chunks,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    return {
        "prompt_hash": prompt_hash,
        "content_hash": content_hash,
    }


def get_resume_metadata(
    old_progress: dict,
    prompt_version: str,
    fingerprints: dict[str, str],
    chunk_count: int,
    reprocess: bool,
) -> tuple[list[dict], bool]:
    """Return valid saved chunk results when extraction can safely resume."""
    old_chunks = old_progress.get("chunk_metadata", [])

    can_resume = (
        not reprocess
        and old_progress.get("prompt_version") == prompt_version
        and old_progress.get("prompt_hash") == fingerprints["prompt_hash"]
        and old_progress.get("content_hash") == fingerprints["content_hash"]
        and old_progress.get("chunk_count") == chunk_count
        and old_progress.get("status") in {"in_progress", "failed"}
        and isinstance(old_chunks, list)
        and old_progress.get("completed_chunks") == len(old_chunks)
        and len(old_chunks) <= chunk_count
    )

    if not can_resume:
        return [], False

    try:
        # Validate saved results before reusing them.
        for item in old_chunks:
            DocMeta.model_validate(item)
    except (TypeError, ValueError):
        return [], False

    return list(old_chunks), True


async def save_progress(
    sessionmaker,
    db_id: int,
    progress: dict,
    metadata: dict | None = None,
) -> None:
    """Persist extraction progress in the document JSON metadata."""
    async with sessionmaker() as session:
        document = await session.get(Document, db_id)

        if document is None:
            raise RuntimeError(f"Document {db_id} disappeared during extraction.")

        updated = dict(document.metadata_ or {})

        if metadata:
            updated.update(metadata)

        updated["metadata_extraction"] = progress
        document.metadata_ = updated
        await session.commit()


async def process_documents(
    limit: int | None,
    retry_failed: bool,
    reprocess: bool,
    prompt_version: str,
    dry_run: bool = False,
    paths: list[str] | None = None,
) -> None:
    # Resolve selected files before connecting to the database.
    selected_external_ids = resolve_selected_external_ids(paths) if paths else None

    settings = get_settings()
    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)

    processed = 0
    failed = 0
    total_chunks = 0
    skipped = 0
    not_selected = 0
    document_rows = []

    try:
        async with sessionmaker() as session:
            documents = (
                (await session.execute(select(Document).order_by(Document.id))).scalars().all()
            )

            documents = [
                document
                for document in documents
                if (document.metadata_ or {}).get("parser") == "pymupdf"
            ]

            document_rows = [
                (
                    document.id,
                    document.external_id,
                    document.title,
                    dict(document.metadata_ or {}),
                )
                for document in documents
            ]

        # Restrict extraction to explicitly selected PDF files.
        if selected_external_ids is not None:
            document_rows = [row for row in document_rows if row[1] in selected_external_ids]

            found_external_ids = {row[1] for row in document_rows}
            missing_external_ids = selected_external_ids - found_external_ids

            if missing_external_ids:
                missing = ", ".join(sorted(missing_external_ids))
                raise ValueError(
                    "These selected PDFs have not been parsed into the database: "
                    f"{missing}. Run scripts/parse_corpus.py first."
                )

        # Identify pending documents before applying the limit.
        pending_rows = [
            row
            for row in document_rows
            if not should_skip(
                row[3].get("metadata_extraction", {}).get("status"),
                retry_failed,
                reprocess,
            )
        ]

        skipped = len(document_rows) - len(pending_rows)

        selected_rows = pending_rows[:limit] if limit is not None else pending_rows
        not_selected = len(pending_rows) - len(selected_rows)

        print(f"Total matching PDF documents: {len(document_rows)}")
        print(f"Pending documents: {len(pending_rows)}")
        print(f"Documents selected: {len(selected_rows)}")

        prompt = load_prompt("extract", prompt_version)

        if not dry_run:
            recorder = create_llm_recorder(sessionmaker)
            gateway = create_llm_gateway(settings, recorder=recorder)

        for db_id, _external_id, title, existing_metadata in selected_rows:
            old_progress = existing_metadata.get("metadata_extraction", {})

            async with sessionmaker() as session:
                page_result = await session.execute(
                    select(Page.text).where(Page.document_id == db_id).order_by(Page.page_no)
                )
                page_texts = page_result.scalars().all()

            chunks = chunk_pages(page_texts)
            fingerprints = create_fingerprints(prompt, chunks)

            if not chunks:
                message = "Document has no parsed page text."

                progress = {
                    "status": "failed",
                    "prompt_version": prompt_version,
                    **fingerprints,
                    "completed_chunks": 0,
                    "chunk_count": 0,
                    "chunk_metadata": [],
                    "error": message,
                }

                if not dry_run:
                    await save_progress(sessionmaker, db_id, progress)

                print(f"Failed: {title} ({message})")
                failed += 1
                continue

            total_chunks += len(chunks)

            print(
                f"\nDocument: {title}"
                f"\n  Pages: {len(page_texts)}"
                f"\n  Chunks: {len(chunks)}"
                f"\n  Characters: {sum(len(chunk) for chunk in chunks)}"
            )

            if dry_run:
                continue

            saved_metadata, can_resume = get_resume_metadata(
                old_progress=old_progress,
                prompt_version=prompt_version,
                fingerprints=fingerprints,
                chunk_count=len(chunks),
                reprocess=reprocess,
            )

            completed_chunks = len(saved_metadata)

            if can_resume:
                print(f"  Resuming from chunk {completed_chunks + 1}")
            else:
                print("  Starting extraction from chunk 1")

            progress = {
                "status": "in_progress",
                "prompt_version": prompt_version,
                **fingerprints,
                "completed_chunks": completed_chunks,
                "chunk_count": len(chunks),
                "chunk_metadata": saved_metadata,
            }

            try:
                for index in range(completed_chunks, len(chunks)):
                    print(f"  Extracting chunk {index + 1}/{len(chunks)}")

                    metadata, result = await extract_metadata(
                        gateway=gateway,
                        prompt=prompt,
                        version=prompt_version,
                        document_text=chunks[index],
                    )

                    saved_metadata.append(metadata.model_dump())

                    progress = {
                        "status": "in_progress",
                        "prompt_version": prompt_version,
                        **fingerprints,
                        "completed_chunks": len(saved_metadata),
                        "chunk_count": len(chunks),
                        "chunk_metadata": saved_metadata,
                        "provider": result.provider,
                        "model": result.model,
                    }

                    # Save after every successful chunk.
                    await save_progress(sessionmaker, db_id, progress)

                chunk_results = [DocMeta.model_validate(item) for item in saved_metadata]
                final_metadata = merge_metadata(chunk_results)

                final_progress = {
                    "status": "completed",
                    "prompt_version": prompt_version,
                    **fingerprints,
                    "completed_chunks": len(chunks),
                    "chunk_count": len(chunks),
                    "provider": progress.get("provider"),
                    "model": progress.get("model"),
                }

                await save_progress(
                    sessionmaker,
                    db_id,
                    final_progress,
                    final_metadata.model_dump(),
                )

                processed += 1

                print(f"Completed: {title}")
                print(f"  Kind: {final_metadata.doc_kind}")
                print(f"  Year: {final_metadata.year}")
                print(f"  Hazards: {final_metadata.hazard}")
                print(f"  Phases: {final_metadata.phase}")

            except Exception as error:
                error_message = str(error)[:1000]

                failed_progress = {
                    **progress,
                    "status": "failed",
                    "error": error_message,
                }

                await save_progress(sessionmaker, db_id, failed_progress)

                failed += 1
                print(f"Failed: {title} ({error_message})")

    finally:
        await engine.dispose()

    print("\nMetadata extraction summary")
    print(f"OK:       {processed}")
    print("Repaired: 0 (no repair mechanism implemented)")
    print(f"Failed:   {failed}")
    print(f"Skipped:  {skipped}")
    print(f"Chunks:   {total_chunks}")
    print(f"Not selected: {not_selected}")
    print(f"Total matching PDF documents: {len(document_rows)}")

    if dry_run:
        print("DRY RUN: no LLM extraction calls were made.")


def main() -> None:
    available_versions = list_versions("extract")

    if not available_versions:
        raise SystemExit("No extraction prompts found.")

    parser = argparse.ArgumentParser(
        description="Extract structured metadata from parsed PDF documents."
    )

    parser.add_argument("--limit", type=int)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--reprocess", action="store_true")
    parser.add_argument("--dry-run", action="store_true")

    parser.add_argument(
        "--path",
        action="append",
        help="Specific parsed PDF path to extract. Can be supplied multiple times.",
    )

    parser.add_argument(
        "--prompt-version",
        default=available_versions[-1],
        choices=available_versions,
    )

    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    asyncio.run(
        process_documents(
            limit=args.limit,
            retry_failed=args.retry_failed,
            reprocess=args.reprocess,
            prompt_version=args.prompt_version,
            dry_run=args.dry_run,
            paths=args.path,
        )
    )


if __name__ == "__main__":
    main()
