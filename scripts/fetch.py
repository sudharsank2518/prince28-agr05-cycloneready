"""Command-line interface for the CycloneReady corpus fetcher."""

import argparse
import asyncio
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cycloneready.ingest.fetch import (  # noqa: E402
    append_urls_to_sources_csv,
    discover_sitemap_urls,
    fetch_sources,
    load_sources,
    register_manual_file,
)


def download_repo(owner_repo, folder, extensions, source, licence):
    """Download selected files from a Git repository using sparse checkout."""

    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", owner_repo):
        raise ValueError("Repository must use OWNER/REPO format.")

    if not source.strip() or not licence.strip():
        raise ValueError("Source and licence are required.")

    if any(
        word in licence.lower()
        for word in (
            "unclear",
            "unknown",
            "not reviewed",
            "permission required",
            "not permitted",
        )
    ):
        raise ValueError("A verified licence or permission is required.")

    selected_extensions = {
        ext.strip().lower() if ext.strip().startswith(".") else f".{ext.strip().lower()}"
        for ext in extensions.split(",")
        if ext.strip()
    }

    if not selected_extensions:
        raise ValueError("Provide at least one file extension.")

    folder = folder.strip("/")

    if not folder or ".." in Path(folder).parts or Path(folder).is_absolute():
        raise ValueError("Provide a valid repository folder.")

    git_url = f"https://github.com/{owner_repo}.git"
    destination = ROOT / "data" / "raw" / owner_repo.replace("/", "_")
    manifest = ROOT / "data" / "manifest.jsonl"

    destination.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="cycloneready-repo-") as temporary:
        clone_dir = Path(temporary) / "repo"

        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--filter=blob:none",
                "--sparse",
                git_url,
                str(clone_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        subprocess.run(
            [
                "git",
                "-C",
                str(clone_dir),
                "sparse-checkout",
                "set",
                folder,
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        selected_folder = clone_dir / folder

        if not selected_folder.is_dir():
            raise ValueError(f"Folder '{folder}' was not found in the repository.")

        copied = 0

        for file_path in selected_folder.rglob("*"):
            if not file_path.is_file() or file_path.is_symlink():
                continue

            if file_path.suffix.lower() not in selected_extensions:
                continue

            relative_path = file_path.relative_to(selected_folder)
            target = destination / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(file_path, target)

            original_url = (
                f"https://github.com/{owner_repo}/blob/HEAD/{folder}/{relative_path.as_posix()}"
            )

            register_manual_file(
                file_path=target,
                source=source,
                licence=licence,
                title=file_path.name,
                original_url=original_url,
                manifest_path=manifest,
            )

            copied += 1

    print(f"Repository: {owner_repo}")
    print(f"Files copied: {copied}")
    print(f"Destination: {destination}")

    return copied


def main():
    parser = argparse.ArgumentParser(description="Polite, resumable CycloneReady corpus downloader")

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    # Download URLs from sources.csv
    urls_parser = subparsers.add_parser(
        "urls",
        help="Download URLs listed in data/sources.csv",
    )
    urls_parser.add_argument(
        "--csv",
        type=Path,
        default=ROOT / "data" / "sources.csv",
    )
    urls_parser.add_argument("--delay", type=float, default=0.5)
    urls_parser.add_argument("--refresh", action="store_true")

    # Register a manually downloaded file
    manual_parser = subparsers.add_parser(
        "manual",
        help="Register a manually downloaded file",
    )
    manual_parser.add_argument("file", type=Path)
    manual_parser.add_argument("--source", required=True)
    manual_parser.add_argument("--licence", required=True)
    manual_parser.add_argument("--title", required=True)
    manual_parser.add_argument("--from-url", required=True)
    manual_parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "data" / "manifest.jsonl",
    )

    # Discover URLs from a sitemap
    sitemap_parser = subparsers.add_parser(
        "sitemap",
        help="Discover sitemap URLs and add them to sources.csv",
    )
    sitemap_parser.add_argument("url")
    sitemap_parser.add_argument("--include", default="")
    sitemap_parser.add_argument("--limit", type=int, default=300)
    sitemap_parser.add_argument("--source", required=True)
    sitemap_parser.add_argument("--licence", required=True)
    sitemap_parser.add_argument("--title", required=True)
    sitemap_parser.add_argument(
        "--csv",
        type=Path,
        default=ROOT / "data" / "sources.csv",
    )

    # Collect selected files from a GitHub repository
    repo_parser = subparsers.add_parser(
        "repo",
        help="Collect selected files from a GitHub repository",
    )
    repo_parser.add_argument("repository", help="GitHub OWNER/REPO")
    repo_parser.add_argument("--path", required=True)
    repo_parser.add_argument(
        "--ext",
        required=True,
        help="File extensions, comma-separated, e.g. .md,.pdf",
    )
    repo_parser.add_argument("--source", required=True)
    repo_parser.add_argument("--licence", required=True)

    args = parser.parse_args()

    # Git repository collection
    if args.command == "repo":
        try:
            download_repo(
                owner_repo=args.repository,
                folder=args.path,
                extensions=args.ext,
                source=args.source,
                licence=args.licence,
            )
        except (
            ValueError,
            OSError,
            subprocess.CalledProcessError,
        ) as error:
            parser.error(str(error))

    # Download URLs from CSV
    elif args.command == "urls":
        if args.delay < 0:
            parser.error("--delay cannot be negative")

        try:
            sources = load_sources(args.csv)

            print(f"Loaded {len(sources)} source(s).")

            results = asyncio.run(
                fetch_sources(
                    sources,
                    delay=args.delay,
                    max_concurrency=4,
                    refresh=args.refresh,
                )
            )

            for result in results:
                print(result)

        except (OSError, ValueError) as error:
            parser.error(str(error))

    # Register a manually downloaded file
    elif args.command == "manual":
        try:
            result = register_manual_file(
                file_path=args.file,
                source=args.source,
                licence=args.licence,
                title=args.title,
                original_url=args.from_url,
                manifest_path=args.manifest,
            )

            print("Manual file registered successfully!")
            print(f"Title: {result['title']}")
            print(f"Source: {result['source']}")
            print(f"File: {result['file_path']}")
            print(f"SHA-256: {result['sha256']}")

        except (FileNotFoundError, ValueError, OSError) as error:
            parser.error(str(error))

    # Discover URLs from sitemap
    elif args.command == "sitemap":
        try:
            if args.limit < 1:
                parser.error("--limit must be at least 1")

            discovered = asyncio.run(
                discover_sitemap_urls(
                    args.url,
                    include=args.include,
                    limit=args.limit,
                )
            )

            added = append_urls_to_sources_csv(
                discovered,
                source=args.source,
                licence=args.licence,
                title=args.title,
                csv_path=args.csv,
            )

            print(f"Discovered URLs: {len(discovered)}")
            print(f"New URLs added: {added}")
            print(f"Already present or filtered: {len(discovered) - added}")

        except (ValueError, PermissionError, OSError) as error:
            parser.error(str(error))


if __name__ == "__main__":
    main()
