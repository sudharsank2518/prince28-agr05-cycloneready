"""Compare PyMuPDF and pypdf on the ten largest eligible PDF files."""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cycloneready.ingest.parse import ParseError, parse_file  # noqa: E402

MANIFEST = ROOT / "data" / "manifest.jsonl"
NOTES = ROOT / "NOTES.md"
LIMIT = 10


def read_pdf_files() -> list[Path]:
    """Read eligible PDF paths from the download manifest."""
    if not MANIFEST.exists():
        print("Manifest not found. No real corpus files are available.")
        return []

    latest = {}

    with MANIFEST.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            url = record.get("url")
            if url:
                latest[url] = record

    paths = []

    for record in latest.values():
        if record.get("status") not in {"downloaded", "not_modified"}:
            continue

        file_path = record.get("file_path")
        if not file_path:
            continue

        path = ROOT / file_path

        if path.is_file() and path.suffix.lower() == ".pdf":
            paths.append(path)

    return sorted(paths, key=lambda path: path.stat().st_size, reverse=True)


def compare_file(path: Path) -> dict:
    """Compare both PDF parsers on one file."""
    result = {
        "file": str(path.relative_to(ROOT)),
        "size_kb": round(path.stat().st_size / 1024, 2),
    }

    for parser_name in ("pymupdf", "pypdf"):
        started = time.perf_counter()

        try:
            parsed = parse_file(path, pdf_parser=parser_name)
            elapsed = time.perf_counter() - started

            result[parser_name] = {
                "pages": len(parsed.pages),
                "characters": sum(len(page.text) for page in parsed.pages),
                "tables": sum(page.tables for page in parsed.pages),
                "seconds": round(elapsed, 3),
                "error": "",
            }

        except ParseError as error:
            result[parser_name] = {
                "pages": 0,
                "characters": 0,
                "tables": 0,
                "seconds": round(time.perf_counter() - started, 3),
                "error": f"{error.reason}: {error.detail}",
            }

    return result


def choose_better(result: dict) -> str:
    """Give a preliminary verdict based on extraction quality."""
    first = result["pymupdf"]
    second = result["pypdf"]

    if first["error"] and second["error"]:
        return "Both failed"

    if first["error"]:
        return "pypdf"

    if second["error"]:
        return "PyMuPDF"

    if first["characters"] > second["characters"]:
        return "PyMuPDF"

    if second["characters"] > first["characters"]:
        return "pypdf"

    if first["tables"] > second["tables"]:
        return "PyMuPDF"

    if second["tables"] > first["tables"]:
        return "pypdf"

    return "Tie — inspect manually"


def write_notes(results: list[dict]) -> None:
    """Append the comparison results to NOTES.md."""
    lines = [
        "",
        "### Day 7 — PDF Parser Comparison",
        "",
        f"Files compared: {len(results)}",
        "",
    ]

    if not results:
        lines.extend(
            [
                "No approved PDF files were available for comparison.",
                "The real ten-file comparison is pending corpus collection and source permissions.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "| File | PyMuPDF pages/chars/tables | pypdf pages/chars/tables | Verdict |",
                "|---|---:|---:|---|",
            ]
        )

        for item in results:
            first = item["pymupdf"]
            second = item["pypdf"]

            lines.append(
                f"| {item['file']} "
                f"| {first['pages']}/{first['characters']}/{first['tables']} "
                f"| {second['pages']}/{second['characters']}/{second['tables']} "
                f"| {choose_better(item)} |"
            )

        lines.extend(
            [
                "",
                "The verdict is preliminary and based on extracted character and table counts.",
                "Manually inspect at least three documents before selecting the preferred parser.",
                "",
            ]
        )

    with NOTES.open("a", encoding="utf-8") as file:
        file.write("\n".join(lines))

    print(f"Comparison notes written to {NOTES.relative_to(ROOT)}")


def main() -> None:
    files = read_pdf_files()[:LIMIT]

    if not files:
        print("No eligible PDF files found. Real comparison is pending.")
        write_notes([])
        return

    print(f"Comparing {len(files)} PDF file(s)...")

    results = []

    for path in files:
        print(f"\nComparing: {path.name}")
        result = compare_file(path)
        results.append(result)

        for parser_name in ("pymupdf", "pypdf"):
            details = result[parser_name]
            if details["error"]:
                print(f"  {parser_name}: FAILED — {details['error']}")
            else:
                print(
                    f"  {parser_name}: pages={details['pages']}, "
                    f"characters={details['characters']}, "
                    f"tables={details['tables']}, "
                    f"time={details['seconds']}s"
                )

        print(f"  Preliminary verdict: {choose_better(result)}")

    write_notes(results)


if __name__ == "__main__":
    main()
