"""Extract clean, structured pages from PDFs, HTML, and text documents."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
import trafilatura
from pypdf import PdfReader

PAGE_CHARS = 3000
MIN_CHARS_PER_PAGE = 50

TEXT_TYPES = {".txt", ".md", ".rst", ".adoc", ".asciidoc"}
DATA_TYPES = {".csv", ".json", ".xml"}


@dataclass
class ParsedPage:
    page_no: int
    text: str
    headings: list[str] = field(default_factory=list)
    tables: int = 0


@dataclass
class ParsedDoc:
    parser: str
    kind: str
    title: str
    pages: list[ParsedPage]


class ParseError(Exception):
    """A file could not be parsed."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(detail or reason)


def clean_text(value: str) -> str:
    """Normalize Unicode and remove common extraction artefacts."""
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\x00", "").replace("\u00ad", "")
    value = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _remove_repeated_headers(pages: list[str]) -> list[str]:
    """Remove lines repeated at the top or bottom of most PDF pages."""
    if len(pages) < 3:
        return pages

    first_lines = Counter()
    last_lines = Counter()

    for page in pages:
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        if lines:
            first_lines[lines[0]] += 1
            last_lines[lines[-1]] += 1

    threshold = max(3, len(pages) // 2)
    repeated = {line for line, count in (first_lines + last_lines).items() if count >= threshold}

    cleaned = []
    for page in pages:
        lines = page.splitlines()
        while lines and lines[0].strip() in repeated:
            lines.pop(0)
        while lines and lines[-1].strip() in repeated:
            lines.pop()
        cleaned.append("\n".join(lines))

    return cleaned


def _split_pages(text: str) -> list[str]:
    """Split long non-paginated documents into manageable pseudo-pages."""
    text = clean_text(text)
    if not text:
        return []

    chunks = []
    while len(text) > PAGE_CHARS:
        boundary = text.rfind("\n", 0, PAGE_CHARS)
        if boundary < PAGE_CHARS // 2:
            boundary = PAGE_CHARS
        chunks.append(text[:boundary].strip())
        text = text[boundary:].strip()

    if text:
        chunks.append(text)

    return chunks


def _markdown_headings(text: str) -> tuple[str, list[str]]:
    """Extract Markdown headings and their section paths."""
    headings = []
    output = []
    current: list[str] = []
    in_code = False

    for line in text.splitlines():
        stripped = line.strip()

        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code = not in_code
            output.append(line)
            continue

        if not in_code:
            match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", stripped)
            if match:
                level = len(match.group(1))
                heading = match.group(2).strip()
                current = current[: level - 1]
                current.append(heading)
                headings = current.copy()
                output.append(line)
                continue

        output.append(line)

    return "\n".join(output), headings


def _convert_markup(text: str, suffix: str) -> str:
    """Convert simple RST and AsciiDoc headings to Markdown."""
    lines = text.splitlines()
    output = []

    for index, line in enumerate(lines):
        stripped = line.strip()

        if suffix == ".adoc" or suffix == ".asciidoc":
            match = re.match(r"^(=+)\s+(.+)$", stripped)
            if match:
                level = min(len(match.group(1)), 6)
                output.append(f"{'#' * level} {match.group(2)}")
                continue

        if suffix == ".rst" and index + 1 < len(lines):
            underline = lines[index + 1].strip()
            if (
                stripped
                and len(underline) >= 3
                and len(set(underline)) == 1
                and underline[0] in "=-~^\"'`:#*+"
            ):
                level = 1 if underline[0] in "=-" else 2
                output.append(f"{'#' * level} {stripped}")
                continue

        output.append(line)

    return "\n".join(output)


def _markdown_pages(text: str) -> list[ParsedPage]:
    """Create pages while preserving the active heading path."""
    chunks = _split_pages(text)
    pages = []
    current: list[str] = []

    for page_no, chunk in enumerate(chunks, start=1):
        _, page_headings = _markdown_headings(chunk)

        if page_headings:
            current = page_headings

        pages.append(
            ParsedPage(
                page_no=page_no,
                text=clean_text(chunk),
                headings=current.copy(),
            )
        )

    return pages


def _table_to_markdown(table: list[list[str]]) -> str:
    """Convert extracted table rows into Markdown."""
    rows = [
        [str(cell or "").replace("|", r"\|").replace("\n", " ").strip() for cell in row]
        for row in table
    ]

    if not rows:
        return ""

    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]

    result = ["| " + " | ".join(rows[0]) + " |"]
    result.append("| " + " | ".join(["---"] * width) + " |")

    for row in rows[1:]:
        result.append("| " + " | ".join(row) + " |")

    return "\n".join(result)


def _parse_pdf_pymupdf(path: Path) -> ParsedDoc:
    """Extract PDF text, font-based headings, and detected tables."""
    raw_pages = []
    page_tables = []
    page_headings = []

    try:
        document = pymupdf.open(path)
    except Exception as exc:
        raise ParseError("corrupt", str(exc)) from exc

    with document:
        if document.needs_pass:
            raise ParseError("encrypted", "PDF requires a password.")

        for page in document:
            blocks = page.get_text("dict")["blocks"]
            lines = []
            headings = []

            font_sizes = [
                span["size"]
                for block in blocks
                if "lines" in block
                for line in block["lines"]
                for span in line["spans"]
                if span["text"].strip()
            ]
            normal_size = sorted(font_sizes)[len(font_sizes) // 2] if font_sizes else 0

            for block in blocks:
                if "lines" not in block:
                    continue

                for line in block["lines"]:
                    spans = line["spans"]
                    content = "".join(span["text"] for span in spans).strip()

                    if not content:
                        continue

                    lines.append(content)

                    largest = max((span["size"] for span in spans), default=0)
                    bold = any("bold" in span["font"].lower() for span in spans)

                    if content and (
                        largest >= normal_size * 1.2 or (bold and largest >= normal_size)
                    ):
                        headings.append(content)

            table_markdown = []
            table_count = 0

            try:
                found_tables = page.find_tables()
                for table in found_tables.tables:
                    markdown = _table_to_markdown(table.extract())
                    if markdown:
                        table_markdown.append(markdown)
                        table_count += 1
            except Exception:
                pass

            page_text = "\n".join(lines)
            if table_markdown:
                page_text += "\n\n" + "\n\n".join(table_markdown)

            raw_pages.append(clean_text(page_text))
            page_tables.append(table_count)
            page_headings.append(headings)

    if not raw_pages or sum(len(page) for page in raw_pages) < MIN_CHARS_PER_PAGE:
        raise ParseError("no_text_layer", "PDF contains no usable text layer.")

    raw_pages = _remove_repeated_headers(raw_pages)

    pages = []
    current_headings: list[str] = []

    for page_no, content in enumerate(raw_pages, start=1):
        if page_headings[page_no - 1]:
            current_headings = page_headings[page_no - 1].copy()

        pages.append(
            ParsedPage(
                page_no=page_no,
                text=content,
                headings=current_headings.copy(),
                tables=page_tables[page_no - 1],
            )
        )

    return ParsedDoc(
        parser="pymupdf",
        kind="pdf",
        title=path.stem,
        pages=pages,
    )


def _parse_pdf_pypdf(path: Path) -> ParsedDoc:
    """Alternative text-only PDF parser."""
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise ParseError("corrupt", str(exc)) from exc

    if reader.is_encrypted:
        try:
            if not reader.decrypt(""):
                raise ParseError("encrypted", "PDF requires a password.")
        except ParseError:
            raise
        except Exception as exc:
            raise ParseError("encrypted", str(exc)) from exc

    raw_pages = [clean_text(page.extract_text() or "") for page in reader.pages]

    if not raw_pages or sum(len(page) for page in raw_pages) < MIN_CHARS_PER_PAGE:
        raise ParseError("no_text_layer", "PDF contains no usable text layer.")

    raw_pages = _remove_repeated_headers(raw_pages)

    pages = [
        ParsedPage(page_no=index, text=content) for index, content in enumerate(raw_pages, start=1)
    ]

    return ParsedDoc(
        parser="pypdf",
        kind="pdf",
        title=path.stem,
        pages=pages,
    )


def _parse_html(path: Path) -> ParsedDoc:
    """Extract readable article content from an HTML file."""
    html = path.read_text(encoding="utf-8", errors="replace")
    extracted = trafilatura.extract(
        html,
        output_format="markdown",
        include_tables=True,
        include_links=False,
    )

    if not extracted or not extracted.strip():
        raise ParseError("empty", "HTML contains no extractable content.")

    pages = _markdown_pages(clean_text(extracted))

    return ParsedDoc(
        parser="trafilatura",
        kind="html",
        title=path.stem,
        pages=pages,
    )


def _parse_text(path: Path) -> ParsedDoc:
    """Extract text, Markdown headings, and section paths."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    text = clean_text(_convert_markup(text, path.suffix.lower()))

    if not text:
        raise ParseError("empty", "File contains no text.")

    pages = _markdown_pages(text)

    return ParsedDoc(
        parser="text",
        kind=path.suffix.lower().lstrip("."),
        title=path.stem,
        pages=pages,
    )


def _parse_data(path: Path) -> ParsedDoc:
    """Read structured data files as text."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    text = clean_text(text)

    if not text:
        raise ParseError("empty", "File contains no data.")

    pages = _markdown_pages(text)

    return ParsedDoc(
        parser="text",
        kind=path.suffix.lower().lstrip("."),
        title=path.stem,
        pages=pages,
    )


def parse_file(path: str | Path, pdf_parser: str = "pymupdf") -> ParsedDoc:
    """Parse a supported file and normalize failures into ParseError."""
    path = Path(path)

    if not path.is_file():
        raise ParseError("corrupt", f"File does not exist: {path}")

    suffix = path.suffix.lower()

    try:
        if suffix == ".pdf":
            if pdf_parser == "pymupdf":
                return _parse_pdf_pymupdf(path)
            if pdf_parser == "pypdf":
                return _parse_pdf_pypdf(path)
            raise ParseError("unsupported_type", f"Unknown PDF parser: {pdf_parser}")

        if suffix in {".html", ".htm"}:
            return _parse_html(path)

        if suffix in TEXT_TYPES:
            return _parse_text(path)

        if suffix in DATA_TYPES:
            return _parse_data(path)

        raise ParseError("unsupported_type", f"Unsupported file extension: {suffix}")

    except ParseError:
        raise
    except UnicodeDecodeError as exc:
        raise ParseError("empty", str(exc)) from exc
    except Exception as exc:
        raise ParseError("corrupt", str(exc)) from exc
