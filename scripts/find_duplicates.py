"""Find downloaded files with identical SHA-256 checksums."""

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "manifest.jsonl"


def find_duplicates():
    """Find duplicate files using their SHA-256 checksums."""

    if not MANIFEST.exists():
        print("Manifest not found. No corpus files have been registered yet.")
        return

    latest_records = {}

    with MANIFEST.open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            url = record.get("url")

            if url:
                latest_records[url] = record

    hashes = defaultdict(list)

    for record in latest_records.values():
        if record.get("status") not in {"downloaded", "not_modified"}:
            continue

        sha256 = record.get("sha256")
        file_path = record.get("file_path")

        if sha256 and file_path:
            hashes[sha256].append(file_path)

    duplicates = {digest: paths for digest, paths in hashes.items() if len(paths) > 1}

    if not duplicates:
        print("No duplicate files found.")
        return

    print(f"Duplicate groups found: {len(duplicates)}")

    for digest, paths in duplicates.items():
        print(f"\nSHA-256: {digest}")

        for path in paths:
            print(f"  - {path}")

    print(f"\nTotal duplicate groups: {len(duplicates)}")


if __name__ == "__main__":
    find_duplicates()
