"""Integration tests for storing parsed documents and parsing failures."""

import pytest
from sqlalchemy import select

from cycloneready.config import Settings
from cycloneready.db.models import Document, Page, ParseFailure
from cycloneready.db.session import make_engine, make_sessionmaker
from cycloneready.ingest.parse import ParsedDoc, ParsedPage
from cycloneready.ingest.store import save_document, save_failure


@pytest.fixture
async def db_session(database_url):
    """Provide a clean PostgreSQL session for each test."""
    settings = Settings(app_env="ci", database_url=database_url, _env_file=None)
    engine = make_engine(settings)

    try:
        async with make_sessionmaker(engine)() as session, session.begin():
            await session.execute(select(ParseFailure))
            await session.execute(Page.__table__.delete())
            await session.execute(Document.__table__.delete())
            await session.execute(ParseFailure.__table__.delete())
            yield session
    finally:
        await engine.dispose()


async def test_save_document_stores_pages_and_headings(db_session):
    parsed = ParsedDoc(
        parser="pymupdf",
        kind="pdf",
        title="Cyclone Safety Guide",
        pages=[
            ParsedPage(
                page_no=1,
                text="Cyclone preparedness information.",
                headings=["Cyclone Safety", "Preparation"],
                tables=1,
            ),
            ParsedPage(
                page_no=2,
                text="Flood safety information.",
                headings=["Cyclone Safety", "Flood Safety"],
            ),
        ],
    )

    document = await save_document(
        db_session,
        path="data/raw/test/guide.pdf",
        sha256="a" * 64,
        source_url="https://example.com/guide.pdf",
        licence="CC BY 4.0",
        parsed=parsed,
    )

    pages = list(
        (
            await db_session.scalars(
                select(Page).where(Page.document_id == document.id).order_by(Page.page_no)
            )
        ).all()
    )

    assert document.title == "Cyclone Safety Guide"
    assert document.doc_type == "pdf"
    assert document.metadata_["parser"] == "pymupdf"
    assert document.metadata_["pages"] == 2
    assert document.metadata_["tables"] == 1
    assert len(pages) == 2
    assert pages[0].page_no == 1
    assert pages[0].headings == ["Cyclone Safety", "Preparation"]
    assert pages[1].headings == ["Cyclone Safety", "Flood Safety"]


async def test_save_failure_increments_attempts(db_session):
    path = "data/raw/test/broken.pdf"

    await save_failure(
        db_session,
        path=path,
        sha256="b" * 64,
        source_url="https://example.com/broken.pdf",
        reason="corrupt",
        detail="Invalid PDF structure",
    )

    await save_failure(
        db_session,
        path=path,
        sha256="b" * 64,
        source_url="https://example.com/broken.pdf",
        reason="no_text_layer",
        detail="No readable text found",
    )

    failure = await db_session.scalar(select(ParseFailure).where(ParseFailure.path == path))

    assert failure is not None
    assert failure.attempts == 2
    assert failure.reason == "no_text_layer"
    assert failure.detail == "No readable text found"


async def test_successful_parse_clears_previous_failure(db_session):
    path = "data/raw/test/recovered.pdf"

    await save_failure(
        db_session,
        path=path,
        sha256="c" * 64,
        source_url="https://example.com/recovered.pdf",
        reason="corrupt",
        detail="Initial parsing failed",
    )

    parsed = ParsedDoc(
        parser="pymupdf",
        kind="pdf",
        title="Recovered Guide",
        pages=[
            ParsedPage(
                page_no=1,
                text="Recovered cyclone safety information.",
                headings=["Safety"],
            )
        ],
    )

    document = await save_document(
        db_session,
        path=path,
        sha256="c" * 64,
        source_url="https://example.com/recovered.pdf",
        licence="CC BY 4.0",
        parsed=parsed,
    )

    failure = await db_session.scalar(select(ParseFailure).where(ParseFailure.path == path))

    assert document.title == "Recovered Guide"
    assert failure is None


async def test_reingestion_preserves_extracted_metadata(db_session):
    parsed = ParsedDoc(
        parser="pymupdf",
        kind="pdf",
        title="Cyclone Safety Guide",
        pages=[
            ParsedPage(
                page_no=1,
                text="Cyclone preparedness information.",
                headings=["Cyclone Safety"],
            )
        ],
    )

    document = await save_document(
        db_session,
        path="data/raw/test/metadata-guide.pdf",
        sha256="d" * 64,
        source_url="https://example.com/metadata-guide.pdf",
        licence="CC BY 4.0",
        parsed=parsed,
    )

    document.metadata_ = {
        **document.metadata_,
        "doc_kind": "guideline",
        "year": 2024,
        "topics": ["cyclone preparedness"],
    }
    await db_session.flush()

    updated = await save_document(
        db_session,
        path="data/raw/test/metadata-guide.pdf",
        sha256="d" * 64,
        source_url="https://example.com/metadata-guide.pdf",
        licence="CC BY 4.0",
        parsed=parsed,
    )

    assert updated.metadata_["doc_kind"] == "guideline"
    assert updated.metadata_["year"] == 2024
    assert updated.metadata_["topics"] == ["cyclone preparedness"]
    assert updated.metadata_["parser"] == "pymupdf"
