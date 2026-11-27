from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from cycloneready.api.deps import get_db_session
from cycloneready.api.main import create_app
from cycloneready.config import Settings


def test_health_is_ok(client):
    r = client.get("/health")

    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["app"] == "cycloneready"
    assert r.json()["version"] == "dev"


def test_health_supports_head_request(client):
    r = client.head("/health")

    assert r.status_code == 200
    assert r.content == b""


def test_health_reports_custom_git_sha(tmp_path):
    test_sha = "abc123def456"  # pragma: allowlist secret

    settings = Settings(
        app_env="ci",
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        git_sha=test_sha,
    )

    app = create_app(settings)

    with TestClient(app) as c:
        r = c.get("/health")

    assert r.status_code == 200
    assert r.json()["version"] == test_sha


def test_ready_when_database_available(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["checks"]["database"] is True


def test_ready_is_503_when_database_unavailable(tmp_path):
    settings = Settings(
        app_env="ci",
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
    )

    app = create_app(settings)

    async def unavailable_session():
        session = AsyncMock()
        session.execute.side_effect = SQLAlchemyError("Database unavailable")
        yield session

    app.dependency_overrides[get_db_session] = unavailable_session

    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        assert c.get("/ready").status_code == 503


def test_list_documents_paginates(client):
    r = client.get("/v1/documents", params={"limit": 2})
    body = r.json()
    assert r.status_code == 200
    assert body["total"] == 3
    assert len(body["items"]) == 2


def test_search_filters_records(client):
    r = client.get("/v1/documents", params={"q": "beta"})
    assert [d["id"] for d in r.json()["items"]] == ["002"]


def test_get_document_found(client):
    r = client.get("/v1/documents/001")
    assert r.status_code == 200
    assert r.json()["title"] == "Alpha guideline"


def test_missing_document_is_problem_details(client):
    r = client.get("/v1/documents/999")
    assert r.status_code == 404
    assert r.headers["content-type"] == "application/problem+json"
    body = r.json()
    assert body["status"] == 404
    assert body["title"] == "Not Found"
    assert body["request_id"] == r.headers["X-Request-ID"]


def test_bad_limit_is_422_problem(client):
    r = client.get("/v1/documents", params={"limit": 0})
    assert r.status_code == 422
    assert r.json()["errors"][0]["field"] == "query.limit"


def test_request_id_is_echoed(client):
    r = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"


def test_app_refuses_to_start_without_app_env(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_sort_documents_by_title(client):
    r = client.get("/v1/documents", params={"sort": "title"})

    assert r.status_code == 200
    titles = [d["title"] for d in r.json()["items"]]

    assert titles == sorted(titles)


def test_sort_documents_by_published_on_descending(client):
    r = client.get("/v1/documents", params={"sort": "-published_on"})

    assert r.status_code == 200

    items = r.json()["items"]

    assert r.json()["total"] == 3

    dates = [item["published_on"] for item in items]

    assert dates == [
        "2025-12-10",
        "2024-06-20",
        "2023-01-15",
    ]


def test_get_document_pages_paginates(client):
    first = client.get("/v1/documents/001/pages", params={"limit": 2})
    assert first.status_code == 200

    body = first.json()
    assert body["document_id"] == "001"
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert [page["page_no"] for page in body["items"]] == [1, 2]
    assert body["items"][0]["headings"] == ["Introduction"]
    assert body["items"][1]["headings"] == ["Guidelines", "Section 1"]

    second = client.get(
        "/v1/documents/001/pages",
        params={"limit": 2, "offset": 2},
    )
    assert second.status_code == 200
    assert [page["page_no"] for page in second.json()["items"]] == [3]


def test_get_document_pages_missing_document(client):
    response = client.get("/v1/documents/999/pages")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["status"] == 404


def test_get_document_pages_rejects_invalid_limit(client):
    response = client.get(
        "/v1/documents/001/pages",
        params={"limit": 0},
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "query.limit"
