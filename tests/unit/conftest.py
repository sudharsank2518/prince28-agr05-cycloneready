import asyncio
import hashlib
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from cycloneready.api.main import create_app
from cycloneready.config import Settings
from cycloneready.db.models import Base, Document, Page

SAMPLE = [
    {
        "id": "001",
        "title": "Alpha guideline",
        "year": 2023,
        "published_on": "2023-01-15",
    },
    {
        "id": "002",
        "title": "Beta circular",
        "year": 2024,
        "published_on": "2024-06-20",
    },
    {
        "id": "003",
        "title": "Gamma notice",
        "year": 2025,
        "published_on": "2025-12-10",
    },
]


@pytest.fixture
def client(tmp_path):
    database_path = tmp_path / "test.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    settings = Settings(
        app_env="ci",
        database_url=database_url,
        admin_token="test-admin-token",
    )

    app = create_app(settings)

    async def setup_database():
        async with app.state.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with app.state.sessionmaker() as session:
            for record in SAMPLE:
                fingerprint = hashlib.sha256(
                    json.dumps(record, sort_keys=True).encode("utf-8")
                ).hexdigest()

                document = Document(
                    external_id=record["id"],
                    title=record["title"],
                    doc_type="record",
                    published_on=date.fromisoformat(record["published_on"]),
                    sha256=fingerprint,
                    metadata_={"year": record["year"]},
                )
                session.add(document)

                if record["id"] == "001":
                    session.add_all(
                        [
                            Page(
                                document=document,
                                page_no=1,
                                text="Alpha page one",
                                headings=["Introduction"],
                            ),
                            Page(
                                document=document,
                                page_no=2,
                                text="Alpha page two",
                                headings=["Guidelines", "Section 1"],
                            ),
                            Page(
                                document=document,
                                page_no=3,
                                text="Alpha page three",
                                headings=["Conclusion"],
                            ),
                        ]
                    )

            await session.commit()

    asyncio.run(setup_database())

    with TestClient(app) as test_client:
        yield test_client
