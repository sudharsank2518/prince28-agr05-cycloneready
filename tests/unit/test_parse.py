"""Unit tests for document parsing."""

from pathlib import Path

import pymupdf
import pytest

from cycloneready.ingest.parse import (
    ParseError,
    clean_text,
    parse_file,
)


def create_pdf(path: Path, pages: list[str]) -> Path:
    """Create a small PDF for parser tests."""
    document = pymupdf.open()

    for content in pages:
        page = document.new_page()
        page.insert_text((50, 50), content, fontsize=11)

    document.save(path)
    document.close()
    return path


def test_pdf_page_numbers_and_text(tmp_path: Path):
    path = create_pdf(
        tmp_path / "guide.pdf",
        ["Flood safety information " * 5, "Cyclone preparedness information " * 5],
    )

    parsed = parse_file(path)

    assert parsed.kind == "pdf"
    assert parsed.parser == "pymupdf"
    assert len(parsed.pages) == 2
    assert parsed.pages[0].page_no == 1
    assert parsed.pages[1].page_no == 2
    assert "Flood safety" in parsed.pages[0].text


def test_pdf_pypdf_alternative(tmp_path: Path):
    path = create_pdf(
        tmp_path / "guide.pdf",
        ["Cyclone preparedness information " * 5],
    )

    parsed = parse_file(path, pdf_parser="pypdf")

    assert parsed.parser == "pypdf"
    assert len(parsed.pages) == 1
    assert "Cyclone preparedness" in parsed.pages[0].text


def test_corrupt_pdf(tmp_path: Path):
    path = tmp_path / "broken.pdf"
    path.write_text("This is not a PDF file.")

    with pytest.raises(ParseError) as error:
        parse_file(path)

    assert error.value.reason == "corrupt"


def test_pdf_without_text_layer(tmp_path: Path):
    path = tmp_path / "empty.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(path)
    document.close()

    with pytest.raises(ParseError) as error:
        parse_file(path)

    assert error.value.reason == "no_text_layer"


def test_encrypted_pdf(tmp_path: Path):
    path = tmp_path / "encrypted.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((50, 50), "Encrypted document content " * 5)
    document.save(
        path,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw="secret",
    )
    document.close()

    with pytest.raises(ParseError) as error:
        parse_file(path)

    assert error.value.reason == "encrypted"


def test_clean_text_removes_extraction_artifacts():
    value = "Cyclone\u00ad safety\x00\ninformation"

    cleaned = clean_text(value)

    assert "\x00" not in cleaned
    assert "\u00ad" not in cleaned
    assert "Cyclone safety" in cleaned


def test_clean_text_preserves_tamil_unicode():
    value = "தமிழ்நாடு பேரிடர் மேலாண்மை"

    assert clean_text(value) == value


def test_markdown_heading_paths(tmp_path: Path):
    path = tmp_path / "guide.md"
    path.write_text(
        "# Cyclone\n\n## Safety\n\nStay indoors.\n\n### Flood\n\nMove to higher ground.",
        encoding="utf-8",
    )

    parsed = parse_file(path)

    assert parsed.pages[0].headings == ["Cyclone", "Safety", "Flood"]
    assert "Move to higher ground" in parsed.pages[0].text


def test_markdown_code_fence_is_not_heading(tmp_path: Path):
    path = tmp_path / "guide.md"
    path.write_text(
        "# Real heading\n\n```markdown\n# Not a heading\n```\n",
        encoding="utf-8",
    )

    parsed = parse_file(path)

    assert parsed.pages[0].headings == ["Real heading"]


def test_rst_headings(tmp_path: Path):
    path = tmp_path / "guide.rst"
    path.write_text(
        "Cyclone Safety\n==============\n\nStay indoors.",
        encoding="utf-8",
    )

    parsed = parse_file(path)

    assert parsed.pages[0].headings == ["Cyclone Safety"]


def test_asciidoc_headings(tmp_path: Path):
    path = tmp_path / "guide.adoc"
    path.write_text(
        "= Cyclone Safety\n\n== Before the storm\n\nPrepare an emergency kit.",
        encoding="utf-8",
    )

    parsed = parse_file(path)

    assert parsed.pages[0].headings == ["Cyclone Safety", "Before the storm"]


def test_html_extraction(tmp_path: Path):
    path = tmp_path / "guide.html"
    path.write_text(
        """
        <html>
        <head><title>Cyclone Safety</title></head>
        <body>
        <article>
        <h1>Cyclone Safety</h1>
        <p>Prepare an emergency kit and follow official warnings.</p>
        <p>Keep drinking water and essential medicines ready.</p>
        </article>
        </body>
        </html>
        """,
        encoding="utf-8",
    )

    parsed = parse_file(path)

    assert parsed.kind == "html"
    assert "emergency kit" in parsed.pages[0].text


def test_empty_text_file(tmp_path: Path):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ParseError) as error:
        parse_file(path)

    assert error.value.reason == "empty"


def test_unsupported_file_type(tmp_path: Path):
    path = tmp_path / "guide.exe"
    path.write_text("Some content")

    with pytest.raises(ParseError) as error:
        parse_file(path)

    assert error.value.reason == "unsupported_type"


def test_long_text_is_split_into_pages(tmp_path: Path):
    path = tmp_path / "long.txt"
    path.write_text("Cyclone preparedness information.\n" * 300)

    parsed = parse_file(path)

    assert len(parsed.pages) > 1
    assert parsed.pages[0].page_no == 1
    assert parsed.pages[-1].page_no == len(parsed.pages)


def test_missing_file(tmp_path: Path):
    path = tmp_path / "missing.pdf"

    with pytest.raises(ParseError) as error:
        parse_file(path)

    assert error.value.reason == "corrupt"
