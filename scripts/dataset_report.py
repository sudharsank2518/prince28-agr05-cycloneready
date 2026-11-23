"""Generate CycloneReady dataset and capacity reports."""

import argparse
import json
import math
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "manifest.jsonl"
DATASET_REPORT = ROOT / "DATASET.md"
CAPACITY_REPORT = ROOT / "docs" / "CAPACITY.md"

TARGET_PAGES = 3000
CHARS_PER_TOKEN = 4
CHUNK_TOKENS = 500

USER_AGENT = (
    "examate-student-bot/0.1 "
    "(student project; "
    "+https://github.com/sudharsank2518/prince28-agr05-cycloneready)"
)


class TextExtractor(HTMLParser):
    """Extract readable text from HTML."""

    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript"}:
            self.hidden_depth = max(0, self.hidden_depth - 1)

    def handle_data(self, data):
        if not self.hidden_depth:
            self.parts.append(data)

    def get_text(self):
        return " ".join(self.parts)


def read_manifest():
    """Read the latest manifest record for each URL."""
    latest = {}

    if not MANIFEST.exists():
        return []

    with MANIFEST.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            try:
                record = json.loads(line)
                url = record.get("url")

                if url:
                    latest[url] = record

            except json.JSONDecodeError:
                continue

    return list(latest.values())


def inspect_pdf(path):
    """Return PDF page count, approximate tokens and scanned pages."""
    try:
        reader = PdfReader(str(path), strict=False)
        page_count = len(reader.pages)
        characters = 0
        scanned_pages = 0

        for page in reader.pages:
            page_text = page.extract_text() or ""
            characters += len(page_text.strip())

            if not page_text.strip():
                scanned_pages += 1

        return {
            "pages": page_count,
            "tokens": characters // CHARS_PER_TOKEN,
            "scanned_pages": scanned_pages,
            "error": None,
        }

    except Exception as exc:
        return {
            "pages": 0,
            "tokens": 0,
            "scanned_pages": 0,
            "error": str(exc),
        }


def inspect_text_file(path):
    """Extract approximate tokens from HTML and text files."""
    try:
        content = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        if path.suffix.lower() in {".html", ".htm"}:
            extractor = TextExtractor()
            extractor.feed(content)
            content = extractor.get_text()

        return len(content) // CHARS_PER_TOKEN

    except OSError:
        return 0


def collect_stats(records):
    """Calculate corpus and crawl statistics from manifest entries."""

    sources = defaultdict(
        lambda: {
            "files": 0,
            "bytes": 0,
            "pages": 0,
            "tokens": 0,
        }
    )

    host_durations = defaultdict(float)

    documents = []
    total_files = 0
    total_bytes = 0
    total_pages = 0
    total_tokens = 0
    total_scanned_pages = 0
    extraction_errors = 0
    retry_count = 0
    duration_records = 0

    hashes = defaultdict(list)

    for record in records:
        # Duration includes robots checks, waiting and fetch attempts.
        duration = record.get("duration_seconds")

        if duration is not None:
            try:
                duration = float(duration)

                if math.isfinite(duration) and duration >= 0:
                    host = urlparse(record.get("url", "")).netloc

                    if host:
                        host_durations[host] += duration
                        duration_records += 1

            except (TypeError, ValueError):
                pass

        if record.get("status") not in {"downloaded", "not_modified"}:
            continue

        file_value = record.get("file_path")

        if not file_value:
            continue

        path = Path(file_value)

        if not path.is_absolute():
            path = ROOT / path

        if not path.is_file():
            continue

        size = path.stat().st_size
        pages = 0
        tokens = 0
        scanned_pages = 0
        extraction_error = None

        if path.suffix.lower() == ".pdf":
            result = inspect_pdf(path)
            pages = result["pages"]
            tokens = result["tokens"]
            scanned_pages = result["scanned_pages"]
            extraction_error = result["error"]

            if extraction_error:
                extraction_errors += 1

        elif path.suffix.lower() in {
            ".html",
            ".htm",
            ".txt",
            ".md",
            ".csv",
        }:
            tokens = inspect_text_file(path)

        source = record.get("source", "Unknown")
        licence = record.get("licence", "Not recorded")
        title = record.get("title", path.name)
        digest = record.get("sha256", "")

        sources[source]["files"] += 1
        sources[source]["bytes"] += size
        sources[source]["pages"] += pages
        sources[source]["tokens"] += tokens

        total_files += 1
        total_bytes += size
        total_pages += pages
        total_tokens += tokens
        total_scanned_pages += scanned_pages

        attempts = record.get("attempts", 0) or 0

        if attempts > 1:
            retry_count += 1

        if digest:
            hashes[digest].append(str(path))

        documents.append(
            {
                "title": title,
                "source": source,
                "url": record.get("url", ""),
                "licence": licence,
                "file": (str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)),
                "pages": pages,
                "bytes": size,
                "sha256": digest,
                "scanned_pages": scanned_pages,
                "error": extraction_error,
                "duration_seconds": duration,
            }
        )

    duplicates = {digest: paths for digest, paths in hashes.items() if len(paths) > 1}

    slowest_host = None
    slowest_seconds = None

    if host_durations:
        slowest_host, slowest_seconds = max(
            host_durations.items(),
            key=lambda item: item[1],
        )

    return {
        "sources": dict(sources),
        "documents": documents,
        "files": total_files,
        "bytes": total_bytes,
        "pages": total_pages,
        "tokens": total_tokens,
        "scanned_pages": total_scanned_pages,
        "extraction_errors": extraction_errors,
        "retry_count": retry_count,
        "duplicates": duplicates,
        "host_durations": dict(host_durations),
        "slowest_host": slowest_host,
        "slowest_seconds": slowest_seconds,
        "duration_records": duration_records,
    }


def format_mb(size):
    return size / (1024 * 1024)


def markdown_cell(value):
    """Keep values safe inside Markdown table cells."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def generate_dataset_report(records, stats):
    """Generate DATASET.md."""

    lines = [
        "# CycloneReady Dataset",
        "",
        "## Collection target",
        "",
        "- Start target: NDMA cyclone and urban flood guidelines, plus the Tamil Nadu state plan.",
        f"- Full target: approximately {TARGET_PAGES:,} pages.",
        f"- Collector User-Agent: `{USER_AGENT}`",
        "",
        "## Collection summary",
        "",
        f"- Files collected: {stats['files']}",
        f"- PDF pages: {stats['pages']}",
        f"- Extracted text tokens (approx.): {stats['tokens']:,}",
        f"- Scanned or text-empty PDF pages: {stats['scanned_pages']}",
        f"- Files with PDF extraction errors: {stats['extraction_errors']}",
        f"- Disk usage: {format_mb(stats['bytes']):.2f} MB",
        "",
        "## Source summary",
        "",
        "| Source | Files | Pages | Size (MB) | Licence |",
        "|---|---:|---:|---:|---|",
    ]

    for source, values in sorted(stats["sources"].items()):
        licences = sorted(
            {
                str(record.get("licence", "Not recorded"))
                for record in records
                if record.get("source") == source
            }
        )

        lines.append(
            f"| {markdown_cell(source)} | {values['files']} | "
            f"{values['pages']} | {format_mb(values['bytes']):.2f} | "
            f"{markdown_cell('; '.join(licences))} |"
        )

    lines.extend(
        [
            "",
            "## Document inventory",
            "",
            (
                "| Title | Source | URL | Licence | File | Pages | "
                "Size (MB) | Fetch time (seconds) | SHA-256 |"
            ),
            "|---|---|---|---|---|---:|---:|---:|---|",
        ]
    )

    for doc in stats["documents"]:
        duration_text = (
            f"{doc['duration_seconds']:.3f}"
            if doc["duration_seconds"] is not None
            else "Not recorded"
        )

        lines.append(
            f"| {markdown_cell(doc['title'])} "
            f"| {markdown_cell(doc['source'])} "
            f"| {markdown_cell(doc['url'])} "
            f"| {markdown_cell(doc['licence'])} "
            f"| {markdown_cell(doc['file'])} "
            f"| {doc['pages']} "
            f"| {format_mb(doc['bytes']):.2f} "
            f"| {duration_text} "
            f"| `{doc['sha256']}` |"
        )

    if not stats["documents"]:
        lines.append("| No collected documents yet | - | - | - | - | 0 | 0.00 | - | - |")

    if stats["slowest_host"] is not None:
        slowest_text = f"{stats['slowest_host']} ({stats['slowest_seconds']:.3f} seconds total)"
    else:
        slowest_text = "Not available (no fetch durations recorded yet)"

    lines.extend(
        [
            "",
            "## Source review",
            "",
            "- NDMA: automated access and reproduction permissions require clarification.",
            "- TNSDMA: SSL certificate issue; access and permissions remain unverified.",
            "- IMD/RSMC: reproduction permission requires confirmation.",
            "",
            "## Crawl metrics",
            "",
            f"- Files requiring more than one attempt: {stats['retry_count']}",
            f"- Duplicate SHA-256 groups: {len(stats['duplicates'])}",
            f"- Records with fetch duration: {stats['duration_records']}",
            f"- Slowest host by cumulative fetch time: {slowest_text}",
            "",
            "## Host fetch durations",
            "",
            "| Host | Total recorded fetch time (seconds) |",
            "|---|---:|",
        ]
    )

    if stats["host_durations"]:
        for host, duration in sorted(
            stats["host_durations"].items(),
            key=lambda item: item[1],
            reverse=True,
        ):
            lines.append(f"| {markdown_cell(host)} | {duration:.3f} |")
    else:
        lines.append("| No duration data available | - |")

    lines.extend(
        [
            "",
            "## Duplicate files",
            "",
        ]
    )

    if stats["duplicates"]:
        for digest, paths in stats["duplicates"].items():
            lines.append(f"- SHA-256 `{digest}`: {', '.join(paths)}")
    else:
        lines.append("- No duplicate file hashes detected.")

    lines.extend(
        [
            "",
            "## Known gaps",
            "",
            "- Source permissions must be verified before downloading, "
            "storing or reproducing content.",
            "- The start corpus has not yet been collected.",
            "- Scanned PDFs may require OCR.",
            "- HTML and text files do not contribute to PDF page counts.",
            "- Unknown file formats are not included in extracted text estimates.",
            "",
        ]
    )

    DATASET_REPORT.write_text("\n".join(lines), encoding="utf-8")


def generate_capacity_report(stats, full_pages):
    """Generate docs/CAPACITY.md from measured corpus statistics."""

    pages = stats["pages"]
    tokens = stats["tokens"]

    tokens_per_page = tokens / pages if pages else None

    estimated_tokens = tokens_per_page * full_pages if tokens_per_page is not None else None

    chunks = (
        math.ceil(estimated_tokens / CHUNK_TOKENS)
        if estimated_tokens is not None and estimated_tokens > 0
        else None
    )

    measured_tokens_text = (
        f"{tokens_per_page:.2f}"
        if tokens_per_page is not None
        else "Not available (no PDF sample pages measured)"
    )

    estimated_tokens_text = (
        f"{estimated_tokens:,.0f}"
        if estimated_tokens is not None
        else "Not available (collect a representative sample first)"
    )

    chunks_text = f"{chunks:,}" if chunks is not None else "Not available"

    lines = [
        "# CycloneReady Capacity Estimate",
        "",
        "## Measured corpus",
        "",
        f"- Current PDF pages: {pages:,}",
        f"- Extracted text tokens: {tokens:,}",
        f"- Measured tokens per page: {measured_tokens_text}",
        f"- Current disk usage: {format_mb(stats['bytes']):.2f} MB",
        "",
        "## Full corpus estimate",
        "",
        f"- Target pages: {full_pages:,}",
        f"- Estimated tokens: {estimated_tokens_text}",
        f"- Estimated 500-token chunks: {chunks_text}",
        "",
        "The full-corpus estimate is unavailable until a representative "
        "sample has been collected and measured. It is not zero.",
        "",
        "## Capacity questions",
        "",
        "1. Embedding cost: Not calculated. Select an embedding provider "
        "and use its current published pricing with the measured token count.",
        "2. PostgreSQL capacity: Not verified. Compare measured text and "
        "vector storage against the actual database plan limit.",
        "3. Least certain estimate: Tokens per page. Measure a larger, "
        "representative sample, including scanned PDFs and OCR output.",
        "4. At 10x corpus size: Expect approximately 10x the text, "
        "embedding and storage requirements, subject to chunk overlap, "
        "metadata and index overhead.",
        "",
        "## Limitations",
        "",
        "- Token counts are approximate, using extracted characters divided by four.",
        "- Scanned pages without OCR may contribute zero tokens.",
        "- Chunk estimates use 500 tokens per chunk and do not account for overlap.",
        "- No embedding provider, vector dimension or database storage cost is assumed.",
        "",
    ]

    CAPACITY_REPORT.parent.mkdir(parents=True, exist_ok=True)
    CAPACITY_REPORT.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Generate CycloneReady dataset and capacity reports"
    )

    parser.add_argument(
        "--full-pages",
        type=int,
        default=TARGET_PAGES,
    )

    args = parser.parse_args()

    if args.full_pages < 1:
        parser.error("--full-pages must be positive")

    records = read_manifest()
    stats = collect_stats(records)

    generate_dataset_report(records, stats)
    generate_capacity_report(stats, args.full_pages)

    print("Dataset report generated:", DATASET_REPORT)
    print("Capacity report generated:", CAPACITY_REPORT)
    print("Files:", stats["files"])
    print("Pages:", stats["pages"])
    print("Tokens:", stats["tokens"])
    print("Duplicate SHA-256 groups:", len(stats["duplicates"]))

    if stats["slowest_host"]:
        print(
            "Slowest host:",
            stats["slowest_host"],
            f"({stats['slowest_seconds']:.3f} seconds)",
        )
    else:
        print("Slowest host: Not available (no duration data yet)")


if __name__ == "__main__":
    main()
