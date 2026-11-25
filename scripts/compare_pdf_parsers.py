import csv
import time
from pathlib import Path

from cycloneready.ingest.parse import ParseError, parse_file

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "data" / "test_corpus" / "pdfs"
OUTPUT = ROOT / "data" / "test_corpus" / "pdf_parser_comparison.csv"

PARSERS = ("pymupdf", "pypdf")


def compare_parser(parser: str, files: list[Path]) -> list[dict]:
    results = []

    for path in files:
        started = time.perf_counter()

        try:
            parsed = parse_file(path, pdf_parser=parser)
            elapsed = time.perf_counter() - started

            results.append(
                {
                    "parser": parser,
                    "file": path.name,
                    "status": "success",
                    "pages": len(parsed.pages),
                    "text_chars": sum(len(page.text) for page in parsed.pages),
                    "headings": sum(len(page.headings) for page in parsed.pages),
                    "tables": sum(page.tables for page in parsed.pages),
                    "seconds": round(elapsed, 6),
                    "error": "",
                }
            )

        except ParseError as error:
            elapsed = time.perf_counter() - started

            results.append(
                {
                    "parser": parser,
                    "file": path.name,
                    "status": "failed",
                    "pages": 0,
                    "text_chars": 0,
                    "headings": 0,
                    "tables": 0,
                    "seconds": round(elapsed, 6),
                    "error": f"{error.reason}: {error.detail}",
                }
            )

        except Exception as error:
            elapsed = time.perf_counter() - started

            results.append(
                {
                    "parser": parser,
                    "file": path.name,
                    "status": "unexpected_error",
                    "pages": 0,
                    "text_chars": 0,
                    "headings": 0,
                    "tables": 0,
                    "seconds": round(elapsed, 6),
                    "error": str(error),
                }
            )

    return results


def print_summary(parser: str, results: list[dict]) -> None:
    successful = [row for row in results if row["status"] == "success"]

    print(f"\n--- {parser.upper()} RESULTS ---")
    print(f"Files successful: {len(successful)}/{len(results)}")
    print(f"Pages extracted: {sum(row['pages'] for row in successful)}")
    print(f"Text characters: {sum(row['text_chars'] for row in successful)}")
    print(f"Headings detected: {sum(row['headings'] for row in successful)}")
    print(f"Tables detected: {sum(row['tables'] for row in successful)}")
    print(f"Total time: {sum(row['seconds'] for row in results):.6f} seconds")

    for row in results:
        print(
            f"{row['file']}: {row['status']}, "
            f"pages={row['pages']}, "
            f"chars={row['text_chars']}, "
            f"headings={row['headings']}, "
            f"tables={row['tables']}, "
            f"time={row['seconds']:.6f}s"
        )

        if row["error"]:
            print("  Error:", row["error"])


def main():
    files = sorted(PDF_DIR.glob("*.pdf"))

    if len(files) != 10:
        raise SystemExit(f"Expected exactly 10 PDF files, but found {len(files)}.")

    all_results = []

    for parser in PARSERS:
        results = compare_parser(parser, files)
        all_results.extend(results)
        print_summary(parser, results)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "parser",
                "file",
                "status",
                "pages",
                "text_chars",
                "headings",
                "tables",
                "seconds",
                "error",
            ],
        )
        writer.writeheader()
        writer.writerows(all_results)

    print("\n--- COMPARISON COMPLETE ---")
    print(f"Total runs: {len(all_results)}")
    print(f"CSV report: {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
