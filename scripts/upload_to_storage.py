"""Upload successfully downloaded CycloneReady files to S3 storage."""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cycloneready.storage.s3_client import create_s3_client  # noqa: E402

RAW_DIR = ROOT / "data" / "raw"
MANIFEST_PATH = ROOT / "data" / "manifest.jsonl"

SUCCESS_STATUSES = {"downloaded", "not_modified"}


def get_manifest_files() -> list[Path]:
    """Return existing files recorded as successfully downloaded."""

    if not MANIFEST_PATH.is_file():
        print("No manifest found. No corpus files are ready for upload.")
        return []

    latest_records = {}

    with MANIFEST_PATH.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON in manifest line {line_number}: {error}") from error

            url = record.get("url")
            if url:
                latest_records[url] = record

    files = []

    for record in latest_records.values():
        if record.get("status") not in SUCCESS_STATUSES:
            continue

        file_path = record.get("file_path")

        if not file_path:
            continue

        path = Path(file_path)

        if not path.is_absolute():
            path = ROOT / path

        path = path.resolve()

        # Only allow files inside data/raw.
        try:
            relative_path = path.relative_to(RAW_DIR.resolve())
        except ValueError:
            print(f"Skipped file outside data/raw: {path}")
            continue

        if not path.is_file():
            print(f"Skipped missing file: {relative_path}")
            continue

        if path.name.endswith(".part"):
            print(f"Skipped incomplete file: {relative_path}")
            continue

        files.append(path)

    # Avoid uploading the same physical file twice.
    return sorted(set(files))


def upload_corpus(dry_run: bool = False) -> None:
    """Upload manifest-approved corpus files to object storage."""

    load_dotenv(ROOT / ".env")

    bucket = os.getenv("S3_BUCKET_NAME")

    if not bucket:
        raise ValueError("Missing S3_BUCKET_NAME environment variable.")

    files = get_manifest_files()

    if not files:
        print("No successfully downloaded corpus files found.")
        return

    print(f"\nBucket: {bucket}")
    print(f"Files found: {len(files)}")

    if dry_run:
        for path in files:
            key = path.relative_to(RAW_DIR.resolve()).as_posix()
            print(f"Would upload: {key}")

        print("\nDry run completed. No files uploaded.")
        return

    client = create_s3_client()
    client.head_bucket(Bucket=bucket)

    uploaded = 0
    failed = 0

    for path in files:
        key = path.relative_to(RAW_DIR.resolve()).as_posix()

        try:
            client.upload_file(str(path), bucket, key)
            uploaded += 1
            print(f"Uploaded: {key}")

        except Exception as error:
            failed += 1
            print(f"FAILED: {key} — {error}")

    print("\nUpload summary")
    print(f"Uploaded: {uploaded}")
    print(f"Failed: {failed}")
    print(f"Total: {len(files)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Upload manifest-approved CycloneReady corpus files."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview uploads without sending files.",
    )

    args = parser.parse_args()

    try:
        upload_corpus(dry_run=args.dry_run)
    except (ValueError, FileNotFoundError) as error:
        parser.error(str(error))
