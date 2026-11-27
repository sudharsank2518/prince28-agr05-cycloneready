"""Compare Trafilatura with basic HTML text extraction on official pages."""

import asyncio
import json
import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path

from cycloneready.ingest.fetch import fetch_sources
from cycloneready.ingest.parse import parse_file

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(tempfile.gettempdir()) / "cycloneready-html-benchmark"
RAW_DIR = OUTPUT / "raw"
MANIFEST = OUTPUT / "manifest.jsonl"

SOURCES = [
    {
        "url": "https://sachet.ndma.gov.in/About",
        "source": "NDMA SACHET",
        "licence": "Reuse terms not assessed; benchmark only",
        "title": "NDMA SACHET About",
    },
    {
        "url": "https://mausam.imd.gov.in/responsive/cycloneinformation.php",
        "source": "India Meteorological Department",
        "licence": "Reuse terms not assessed; benchmark only",
        "title": "IMD Cyclone Information",
    },
    {
        "url": "https://mha.gov.in/disaster-management-division",
        "source": "Ministry of Home Affairs",
        "licence": "Reuse terms not assessed; benchmark only",
        "title": "Disaster Management Division",
    },
]

KEYWORDS = {
    "cyclone",
    "flood",
    "warning",
    "evacuation",
    "disaster",
    "shelter",
    "emergency",
    "preparedness",
}


class BasicHTMLText(HTMLParser):
    """Extract visible text without article-specific cleanup."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)

    def get_text(self):
        return " ".join(self.parts)


def metrics(text):
    words = re.findall(r"\b[\w'-]+\b", text.casefold())
    present = sorted(keyword for keyword in KEYWORDS if keyword in words)

    return {
        "characters": len(text),
        "words": len(words),
        "keyword_count": len(present),
        "keywords_found": present,
    }


async def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    print(f"Benchmark directory: {OUTPUT}")
    print("Fetching pages with robots.txt checks and a 2-second delay...")

    results = await fetch_sources(
        SOURCES,
        raw_dir=RAW_DIR,
        manifest_path=MANIFEST,
        delay=2.0,
        max_concurrency=1,
    )

    for result in results:
        print(f"Fetch: {result['url']} -> {result['result']}")

    if not MANIFEST.is_file():
        print("No manifest was created.")
        return

    records = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            records[record["url"]] = record

    report = []

    for source in SOURCES:
        record = records.get(source["url"], {})
        path_value = record.get("file_path")

        if record.get("status") not in {"downloaded", "not_modified"}:
            print(f"\nSkipped: {source['title']} ({record.get('status', 'no record')})")
            continue

        if not path_value or not Path(path_value).is_file():
            print(f"\nMissing downloaded file: {source['title']}")
            continue

        path = Path(path_value)

        try:
            document = parse_file(path)
            trafilatura_text = "\n".join(page.text for page in document.pages)

            html = path.read_text(encoding="utf-8", errors="replace")
            baseline_parser = BasicHTMLText()
            baseline_parser.feed(html)
            baseline_text = baseline_parser.get_text()

            item = {
                "title": source["title"],
                "url": source["url"],
                "file": str(path),
                "trafilatura": metrics(trafilatura_text),
                "basic_html_parser": metrics(baseline_text),
            }
            report.append(item)

            print(f"\n{source['title']}")
            print("  Trafilatura: ", item["trafilatura"])
            print("  Basic HTML:  ", item["basic_html_parser"])

        except Exception as error:
            print(f"\nParse failed for {source['title']}: {error}")

    report_path = OUTPUT / "results.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nSuccessful comparisons: {len(report)}")
    print(f"Results saved to: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
