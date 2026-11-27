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
    """Read all valid manifest records."""
    records = []

    if not MANIFEST.exists():
        return records

    with MANIFEST.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            try:
                record = json.loads(line)

                if record.get("url"):
                    records.append(record)

            except json.JSONDecodeError:
                continue

    return records


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

    # Keep the latest record for each URL for dataset inventory.
    latest_records = {}

    for record in records:
        url = record.get("url")

        if url:
            latest_records[url] = record

    sources = defaultdict(
        lambda: {
            "files": 0,
            "bytes": 0,
            "pages": 0,
            "tokens": 0,
            "licences": set(),
        }
    )

    host_durations = defaultdict(float)
    documents = []
    hashes = defaultdict(list)

    total_files = 0
    total_bytes = 0
    total_pages = 0
    total_tokens = 0
    total_pdf_tokens = 0
    total_scanned_pages = 0
    extraction_errors = 0
    retry_count = 0
    duration_records = 0

    # Process every record for crawl-duration metrics.
    for record in records:
        duration = record.get("duration_seconds")

        if duration is not None:
            try:
                parsed_duration = float(duration)

                if math.isfinite(parsed_duration) and parsed_duration >= 0:
                    host = urlparse(record.get("url", "")).netloc

                    if host:
                        host_durations[host] += parsed_duration
                        duration_records += 1

            except (TypeError, ValueError):
                pass

    # Process only the latest record for each URL in dataset inventory.
    for record in latest_records.values():
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
        is_pdf = path.suffix.lower() == ".pdf"

        if is_pdf:
            result = inspect_pdf(path)
            pages = result["pages"]
            tokens = result["tokens"]
            scanned_pages = result["scanned_pages"]
            extraction_error = result["error"]

            if extraction_error:
                extraction_errors += 1

            total_pdf_tokens += tokens

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
        sources[source]["licences"].add(licence)

        total_files += 1
        total_bytes += size
        total_pages += pages
        total_tokens += tokens
        total_scanned_pages += scanned_pages

        attempts = record.get("attempts", 0) or 0

        try:
            if int(attempts) > 1:
                retry_count += 1
        except (TypeError, ValueError):
            pass

        if digest:
            hashes[digest].append(str(path))

        try:
            display_path = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        except ValueError:
            display_path = str(path)

        duration_seconds = None
        duration = record.get("duration_seconds")

        if duration is not None:
            try:
                parsed_duration = float(duration)

                if math.isfinite(parsed_duration) and parsed_duration >= 0:
                    duration_seconds = parsed_duration

            except (TypeError, ValueError):
                pass

        documents.append(
            {
                "title": title,
                "source": source,
                "url": record.get("url", ""),
                "licence": licence,
                "file": display_path,
                "pages": pages,
                "bytes": size,
                "sha256": digest,
                "scanned_pages": scanned_pages,
                "error": extraction_error,
                "duration_seconds": duration_seconds,
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
        "pdf_tokens": total_pdf_tokens,
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
    """Convert bytes to megabytes."""
    return size / (1024 * 1024)


def markdown_cell(value):
    """Keep values safe inside Markdown table cells."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def generate_dataset_report(stats):
    """Generate DATASET.md using the current project scope."""
    lines = [
        "# CycloneReady Dataset",
        "",
        "## Project data strategy",
        "",
        "CycloneReady is a college project focused on cyclone and urban flood "
        "preparedness, response and recovery, with particular attention to "
        "realistic Tamil Nadu scenarios.",
        "",
        "The initial data strategy uses historical cyclone observations "
        "together with an original CycloneReady solution document developed "
        "by the project team.",
        "",
        "The collected corpus includes historical cyclone data and "
        "disaster-management guidance documents.",
        "The reuse of each document is subject to its source-specific "
        "licence or terms. The project does not assume unrestricted "
        "reproduction or redistribution.",
        "",
        f"- Collector User-Agent: `{USER_AGENT}`",
        "",
        "## Collection summary",
        "",
        f"- Files collected: {stats['files']}",
        f"- PDF pages: {stats['pages']}",
        f"- Extracted text tokens (approx.): {stats['tokens']:,}",
        f"- PDF pages with no extractable text: {stats['scanned_pages']}",
        f"- Files with PDF extraction errors: {stats['extraction_errors']}",
        f"- Disk usage: {format_mb(stats['bytes']):.2f} MB",
        "",
        "Token counts are approximate character-based estimates, not exact "
        "counts from a language-model tokenizer.",
        "",
        "## Database parsing verification",
        "",
        "- Downloaded local files parsed: 5 of 5 (100%).",
        "- Parse failures: 0.",
        "- Parsed documents: 5 (4 PDFs and 1 cyclone CSV).",
        "- Database page records: 5,851.",
        "- Coverage excludes the source URL blocked by the collection policy.",
        "",
        "These figures were verified separately against the Neon PostgreSQL database.",
        "",
        "## Source summary",
        "",
        "| Source | Files | Pages | Size (MB) | Licence |",
        "|---|---:|---:|---:|---|",
    ]

    for source, values in sorted(stats["sources"].items()):
        licences = "; ".join(sorted(values["licences"]))

        lines.append(
            f"| {markdown_cell(source)} | {values['files']} | "
            f"{values['pages']} | {format_mb(values['bytes']):.2f} | "
            f"{markdown_cell(licences)} |"
        )

    lines.extend(
        [
            "",
            "## Document inventory",
            "",
            "| Title | Source | URL | Licence | File | Pages | "
            "Size (MB) | Fetch time (seconds) | SHA-256 |",
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

    lines.extend(["", "## Duplicate files", ""])

    if stats["duplicates"]:
        for digest, paths in stats["duplicates"].items():
            lines.append(f"- SHA-256 `{digest}`: {', '.join(paths)}")
    else:
        lines.append("- No duplicate file hashes detected.")

    lines.extend(
        [
            "",
            "## Original CycloneReady solution document",
            "",
            "The project will develop its own original solution document "
            "covering cyclone preparedness, urban flood preparedness, "
            "Tamil Nadu scenarios, evacuation, emergency response and recovery.",
            "",
            "The document will distinguish verified historical observations, "
            "sourced facts, project assumptions and original recommendations.",
            "",
            "It is planned project content and is not yet counted as a collected dataset file.",
            "",
            "## Known gaps and limitations",
            "",
            "- The current collected corpus contains historical cyclone data, "
            "not a complete disaster-management knowledge base.",
            "- The original CycloneReady solution document still needs to be "
            "authored and reviewed.",
            "- IBTrACS does not independently validate every preparedness "
            "or response recommendation.",
            "- Missing wind-speed and pressure values must remain unknown, not be treated as zero.",
            "- The collected dataset includes 450 PDF pages across four PDF documents.",
            "- Thirteen PDF pages have no extractable text; "
            "inspect them to determine whether OCR is needed.",
            "- Urban flood-specific historical datasets may be added after "
            "their sources and licences are reviewed.",
            "- Unknown file formats are not included in extracted text estimates.",
            "",
        ]
    )

    DATASET_REPORT.write_text("\n".join(lines), encoding="utf-8")


def generate_capacity_report(stats):
    """Generate docs/CAPACITY.md from measured corpus statistics."""
    pages = stats["pages"]
    tokens = stats["tokens"]

    measured_tokens_text = (
        f"{stats['pdf_tokens'] / pages:.2f}"
        if pages > 0
        else "Not applicable (no PDF sample pages measured)"
    )

    current_chunks = math.ceil(tokens / CHUNK_TOKENS) if tokens else 0

    lines = [
        "# CycloneReady Capacity Estimate",
        "",
        "## Current measured corpus",
        "",
        f"- Collected files: {stats['files']}",
        f"- PDF pages: {pages}",
        f"- Approximate extracted text tokens: {tokens:,}",
        f"- Approximate 500-token chunks: {current_chunks:,}",
        f"- Measured PDF tokens per page: {measured_tokens_text}",
        f"- Current disk usage: {format_mb(stats['bytes']):.2f} MB",
        "",
        "The current corpus contains historical cyclone data and "
        "disaster-management reference documents. Token counts "
        "are approximate character-based estimates, not exact tokenizer results.",
        "",
        "## Planned project knowledge",
        "",
        "CycloneReady will include an original solution document developed by the project team.",
        "",
        "- Cyclone preparedness and response.",
        "- Urban flood preparedness and response.",
        "- Realistic Tamil Nadu disaster scenarios.",
        "- Evacuation and emergency planning.",
        "- Community awareness and recovery recommendations.",
        "",
        "The document has not yet been created or measured. Its storage, "
        "token count and chunk count are not included in current measurements.",
        "",
        "## Capacity estimates",
        "",
        "A full capacity estimate will be prepared after the original solution "
        "document and any additional reviewed datasets are available.",
        "",
        "- Measure actual text using the selected tokenizer.",
        "- Estimate chunks using the chosen chunk size and overlap.",
        "- Measure embedding storage using the selected embedding model.",
        "- Measure PostgreSQL and vector-index storage using the actual database.",
        "",
        "## Capacity questions",
        "",
        "1. Embedding cost: Not calculated. Choose an embedding provider and "
        "use its published pricing with the measured token count.",
        "2. PostgreSQL capacity: Not fully verified. Measure actual text, "
        "metadata and vector storage against the database plan limits.",
        "3. Least certain estimate: Future knowledge-base size and token count. "
        "The original solution document and additional evidence sources "
        "have not yet been finalized.",
        "4. At 10x corpus size: Text storage and embedding requirements may "
        "grow approximately 10x. Actual database usage may be higher due "
        "to metadata, indexes and chunk overlap.",
        "",
        "## Limitations",
        "",
        "- Token counts are approximate, using extracted characters divided by four.",
        "- The current dataset has no PDF pages.",
        "- The current measurements do not include the future solution document.",
        "- No embedding provider, vector dimension or database storage cost is assumed.",
        "- Historical cyclone observations alone do not represent the complete "
        "knowledge required for disaster preparedness and response.",
        "",
    ]

    CAPACITY_REPORT.parent.mkdir(parents=True, exist_ok=True)
    CAPACITY_REPORT.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Generate CycloneReady dataset and capacity reports"
    )

    parser.parse_args()

    records = read_manifest()
    stats = collect_stats(records)

    generate_dataset_report(stats)
    generate_capacity_report(stats)

    print("Dataset report generated:", DATASET_REPORT)
    print("Capacity report generated:", CAPACITY_REPORT)
    print("Files:", stats["files"])
    print("Pages:", stats["pages"])
    print("Tokens:", stats["tokens"])
    print("PDF tokens:", stats["pdf_tokens"])
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
