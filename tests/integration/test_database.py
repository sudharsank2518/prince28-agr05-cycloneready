import json
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from cycloneready.api.main import create_app
from cycloneready.config import Settings
from cycloneready.db.models import Document
from cycloneready.db.repository import DocumentRepository
from cycloneready.db.session import make_engine, make_sessionmaker

ROWS = [
    {
        "id": "001",
        "title": "Alpha",
        "doc_kind": "circular",
        "year": 2024,
        "hazard": "cyclone",
        "tags": ["a", "b"],
    },
    {
        "id": "002",
        "title": "Beta",
        "doc_kind": "guideline",
        "year": 2025,
        "hazard": "flood",
        "tags": ["b"],
    },
    {
        "id": "003",
        "title": "Gamma",
        "doc_kind": "circular",
        "year": 2025,
        "hazard": "cyclone",
        "tags": [],
    },
]


@pytest.fixture
def settings(database_url):
    return Settings(app_env="ci", database_url=database_url, _env_file=None)


@pytest.fixture
async def seeded(settings):
    """Fresh rows for each test: delete, insert, and hand back the settings."""
    engine = make_engine(settings)

    async with make_sessionmaker(engine)() as session, session.begin():
        await session.execute(text("DELETE FROM documents"))

        for record in ROWS:
            metadata = {key: value for key, value in record.items() if key not in ("id", "title")}

            session.add(
                Document(
                    external_id=record["id"],
                    title=record["title"],
                    sha256=record["id"] * 21,
                    metadata_=metadata,
                )
            )

    await engine.dispose()
    return settings


async def test_migrations_created_the_tables(settings):
    engine = make_engine(settings)

    async with engine.connect() as connection:
        tables = set(
            await connection.scalars(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
        )
        version = await connection.scalar(text("SELECT version_num FROM alembic_version"))

    await engine.dispose()

    assert {"documents", "pages", "alembic_version"} <= tables
    assert version


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"doc_kind": "circular"}, ["001", "003"]),
        ({"year": "2025"}, ["002", "003"]),
        ({"tags": "b"}, ["001", "002"]),
        ({"doc_kind": "circular", "year": "2025"}, ["003"]),
        ({"hazard": "cyclone"}, ["001", "003"]),
        (
            {"doc_kind": "circular", "hazard": "cyclone"},
            ["001", "003"],
        ),
    ],
)
async def test_repository_filters(seeded, filters, expected):
    engine = make_engine(seeded)

    async with make_sessionmaker(engine)() as session:
        total, items = await DocumentRepository(session).list(
            q=None,
            filters=filters,
            limit=10,
            offset=0,
        )

    await engine.dispose()

    assert [item["id"] for item in items] == expected
    assert total == len(expected)


async def test_repository_get_missing_document(seeded):
    engine = make_engine(seeded)

    async with make_sessionmaker(engine)() as session:
        result = await DocumentRepository(session).get("missing-id")

    await engine.dispose()

    assert result is None


def test_api_against_real_database(seeded):
    with TestClient(create_app(seeded)) as client:
        assert client.get("/ready").json()["checks"]["database"] is True
        assert client.get("/v1/documents/002").json()["title"] == "Beta"
        assert client.get("/v1/documents", params={"q": "gamm"}).json()["total"] == 1

        response = client.get(
            "/v1/documents",
            params={"doc_kind": "circular", "hazard": "cyclone"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert [item["id"] for item in data["items"]] == ["001", "003"]


def test_loader_is_idempotent(database_url, tmp_path):
    data = tmp_path / "records.json"

    data.write_text(
        json.dumps([{"id": "L1", "x": 1}, {"id": "L2", "x": 2}]),
        encoding="utf-8",
    )

    env = {
        **os.environ,
        "APP_ENV": "ci",
        "DATABASE_URL": database_url,
        "DATA_FILE": str(data),
    }

    def run() -> str:
        command = [sys.executable, "scripts/load_db.py"]
        return subprocess.run(
            command,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    assert "inserted=2" in run()
    assert "inserted=0 updated=0 unchanged=2" in run()
