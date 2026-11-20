# CycloneReady – Project Notes

## Day 3 – Database and API Integration

### 1. Database Setup

- Migrated CycloneReady from file-based storage to PostgreSQL.
- Used Neon PostgreSQL as the database.
- Used SQLAlchemy async with the `asyncpg` driver.
- Database credentials are stored in `.env`, not committed to Git.

### 2. Database Models

Created two database models:

- `Document`
- `Page`

Added indexes to improve document searching, including a GIN index on the JSONB metadata column.

### 3. Database Migrations

Created and applied three Alembic migrations:

1. `295f4d5aedd8` – Create documents and pages.
2. `e40f406e001b` – Add GIN index on metadata.
3. `c4a59b7fd09f` – Add typed document column, backfill existing values and create a B-tree index.

Verified migration upgrade and downgrade operations.

### 3.1 Stretch Task – Typed Document Column

- Added a dedicated `document` column to the `documents` table.
- Created and applied the third Alembic migration: `c4a59b7fd09f`.
- Backfilled existing document values from the JSONB `metadata` column.
- Added a B-tree index: `ix_documents_document`.
- Updated `scripts/load_db.py` to store the document field in the typed column.
- Updated the document repository to filter using the indexed column.
- Added the `document` query parameter to the `/v1/documents` API endpoint.
- Verified the backfilled values using Neon SQL Editor.
- Verified filtering through Swagger:
  - NDMA filter: 16 records returned.
  - IMD filter: 4 records returned.
- Total verified records: 20.
- Typed-column filtering: Passed.

### 4. Data Loading

Created `scripts/load_db.py` to load sample JSON records into PostgreSQL.

Verified idempotency:

- First run: 20 inserted.
- Second run: 20 unchanged.
- After modifying one record: 1 updated and 19 unchanged.

The loader also supports the `--prune` option to delete database records absent from the input file.

### 5. API Integration

Updated the FastAPI application to read documents from PostgreSQL.

Implemented:

- Database session dependency.
- Document repository.
- Document listing and search.
- Document retrieval by ID.
- Database readiness check.
- Filtering by the typed `document` column.

Removed the old `RecordStore` implementation.

### 6. Testing

- Configured SQLite with aiosqlite for API tests.
- Tested health and readiness endpoints.
- Tested document listing, searching, pagination and retrieval.
- Tested error responses and request IDs.
- Latest initial Day 3 test result: 10 tests passed.

### 7. Query Performance

Used `scripts/explain.py` to inspect PostgreSQL query execution plans.

The 20-record dataset resulted in a Sequential Scan. This is expected for a small table because PostgreSQL may consider scanning the table cheaper than using an index.

Latest observed execution time: 0.038 ms.

### 8. Useful Commands

```powershell
uv run alembic current
uv run alembic upgrade head
uv run python scripts/load_db.py
uv run python scripts/load_db.py --prune
uv run python scripts/explain.py
uv run pytest
uv run ruff check .
```

### 9. Important Files

- `src/cycloneready/db/models.py`
- `src/cycloneready/db/session.py`
- `src/cycloneready/db/repository.py`
- `src/cycloneready/db/url.py`
- `src/cycloneready/api/routes/documents.py`
- `migrations/`
- `scripts/load_db.py`
- `scripts/explain.py`
- `tests/`

### 10. Day 3 Status

Database migration, data loading, API integration, initial tests, query performance analysis and the typed document column stretch task have been completed.

- Three Alembic migrations applied successfully.
- PostgreSQL data backfill verified.
- Typed document column and B-tree index verified.
- NDMA and IMD API filters verified.
- Final verification and Git review remain.

---

## Day 4 – Docker Build Evidence

- Docker image: `cycloneready:dev`
- First build time: 92.5 seconds.
- Second build time: 17 seconds.
- Image disk usage: 301 MB (target: below 400 MB).
- Container user: `uid=999(app) gid=999(app)`.
- Non-root user verification: Passed.
- Docker build cache: Verified.
- Dependency installation layer: Cached on rebuild.
- Temporary source code change: Added and reverted successfully.

## Day 4 – Docker Compose Evidence

- Docker Compose services: API, PostgreSQL, Redis and migration.
- PostgreSQL healthcheck: Passed.
- Redis healthcheck: Passed.
- API healthcheck: Passed.
- Migration container: Exited successfully (exit code 0).
- Initial database loading: 20 records inserted.
- API documentation: `/docs` verified.
- Document endpoint: `/v1/documents` verified.
- Health endpoint: `/health` verified.
- Readiness endpoint: `/ready` verified.
- Database failure test: `/health` remained available and `/ready` returned `not_ready`.
- Database recovery test: `/ready` returned `ready` after restarting PostgreSQL.
- Idempotency test: 20 unchanged records after restarting the Compose stack.

## Day 4 – Testing Evidence

- Unit tests: 12 passed.
- Integration tests: 7 passed.
- Total tests: 19 passed.
- Code coverage: 82%.
- Ruff lint and formatting checks: Passed.
- Clean Git clone Docker Compose test: Passed.
- Original project Docker environment: Restored successfully.
- Fresh database migration: Passed.
- Sample records restored: 20 inserted.

## Day 4 – Status

Dockerfile, Docker Compose, PostgreSQL integration, Redis, healthchecks, unit tests, integration tests, coverage, Makefile and README updates completed. Git push and pull request verification remain.

## Day 4 – Stretch Task 1: Neon PostgreSQL

- Docker image tested with Neon PostgreSQL.
- Container started successfully on port 8001.
- API readiness endpoint: Passed.
- Database connection: True.
- Neon PostgreSQL connectivity: Verified.

## Day 4 – Stretch Task 2: Docker Layer Analysis

- Docker image inspected using `docker history`.
- Largest layer: Python virtual environment (`.venv`).
- Layer size: 96.4 MB.
- Python base image size: 87.7 MB.
- System packages layer: 41.4 MB.

## Day 4 – Stretch Task 3: HTML Coverage Report

- Generated HTML coverage report successfully.
- Added a test for retrieving a non-existent document.
- Integration tests: 8 passed.
- Coverage: 100%.
- Missing document handling verified.

## Day 4 – Stretch Task 4: Automatic API Restart

- Added `restart: true` to the API database dependency.
- Validated Docker Compose configuration.
- Restarted PostgreSQL using `docker compose restart db`.
- API restarted automatically.
- Readiness endpoint verified successfully.
- Database connection: True.
