import asyncio
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from cycloneready.api.main import create_app
from cycloneready.config import Settings
from cycloneready.db.models import Base, Document

SAMPLE = [
    {"id": "001", "title": "Alpha guideline", "year": 2023},
    {"id": "002", "title": "Beta circular", "year": 2024},
    {"id": "003", "title": "Gamma notice", "year": 2025},
]


@pytest.fixture
def client(tmp_path):
    database_path = tmp_path / "test.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    settings = Settings(
        app_env="ci",
        database_url=database_url,
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

                session.add(
                    Document(
                        external_id=record["id"],
                        title=record["title"],
                        doc_type="record",
                        sha256=fingerprint,
                        metadata_={"year": record["year"]},
                    )
                )

            await session.commit()

    asyncio.run(setup_database())

    with TestClient(app) as test_client:
        yield test_client
