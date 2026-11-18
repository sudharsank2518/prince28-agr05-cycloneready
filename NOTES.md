# CycloneReady – Day 3 Notes

## 1. Database Setup
- Migrated CycloneReady from file-based storage to PostgreSQL.
- Used Neon PostgreSQL as the database.
- Used SQLAlchemy async with the `asyncpg` driver.
- Database credentials are stored in `.env`, not committed to Git.

## 2. Database Models
Created two database models:
- `Document`
- `Page`

Added indexes to improve document searching, including a GIN index on the JSONB metadata column.

## 3. Database Migrations
Created and applied two Alembic migrations:

1. `295f4d5aedd8` – Create documents and pages.
2. `e40f406e001b` – Add GIN index on metadata.

Verified migration upgrade and downgrade operations.

## 4. Data Loading
Created `scripts/load_db.py` to load sample JSON records into PostgreSQL.

Verified idempotency:
- First run: 20 inserted.
- Second run: 20 unchanged.
- After modifying one record: 1 updated and 19 unchanged.

## 5. API Integration
Updated the FastAPI application to read documents from PostgreSQL.

Implemented:
- Database session dependency.
- Document repository.
- Document listing and search.
- Document retrieval by ID.
- Database readiness check.

Removed the old `RecordStore` implementation.

## 6. Testing
- Configured SQLite with aiosqlite for API tests.
- Tested health and readiness endpoints.
- Tested document listing, searching, pagination and retrieval.
- Tested error responses and request IDs.
- Latest test result: 10 tests passed.

## 7. Query Performance
Used `scripts/explain.py` to inspect PostgreSQL query execution plans.

The 20-record dataset resulted in a Sequential Scan. This is expected for a small table because PostgreSQL may consider scanning the table cheaper than using an index.

Latest observed execution time: 0.038 ms.

## 8. Useful Commands

```powershell
uv run alembic current
uv run alembic upgrade head
uv run python scripts/load_db.py
uv run python scripts/explain.py
uv run pytest
uv run ruff check .
```

## 9. Important Files
- `src/cycloneready/db/models.py`
- `src/cycloneready/db/session.py`
- `src/cycloneready/db/repository.py`
- `src/cycloneready/db/url.py`
- `migrations/`
- `scripts/load_db.py`
- `scripts/explain.py`
- `tests/`

## 10. Status
Database migration, data loading, API integration and initial tests have been completed. Final verification and Git review remain.
