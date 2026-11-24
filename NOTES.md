# CycloneReady – Project Notes

## D03 – Database and API Integration

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
- Integration tests: 8 passed.
- Total tests: 20 passed.
- Code coverage: 100% (HTML coverage report).
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

## Day 4 – Monitoring

- UptimeRobot monitor: CycloneReady API.
- Endpoint: https://cycloneready.onrender.com/health
- Check interval: Every 5 minutes.
- Status: Up.
- Uptime badge: Configured in README.md using a monitor-specific API key.
- API key: Not stored in Git or project files.
- Alerts: Email notifications enabled.

---

## D05 – CI/CD and Going Live

## 1. GitHub Actions – Continuous Integration

- Created `.github/workflows/ci.yml`.
- CI runs automatically on pull requests and pushes to `main`.
- Configured PostgreSQL service for integration testing.
- Linting and tests executed using `poe lint` and `poe cov`.
- Docker image built and pushed to GitHub Container Registry (GHCR).
- Image tagged using the commit SHA and `main`.
- Pre-commit checks executed in CI.
- CI checks passed successfully.

## 2. GitHub Actions – Continuous Deployment

- Created `.github/workflows/cd.yml`.
- Automatic deployment triggered after successful CI on `main`.
- Docker image deployed to Render.
- Added production smoke test to verify the live API.
- Added retry mechanism to handle deployment startup delays.
- Added manual workflow dispatch to support rollback and roll-forward.
- Successful automatic deployments verified through GitHub Actions.

## 3. Production Deployment – Render

- Hosting platform: Render.
- Service name: `cycloneready`.
- Live URL: https://cycloneready.onrender.com
- API documentation: https://cycloneready.onrender.com/docs
- Health endpoint: https://cycloneready.onrender.com/health
- Database: Neon PostgreSQL.
- Production environment variables configured in Render.
- Health endpoint verified successfully.

## 4. GitHub Repository Security

- Configured branch protection for `main`.
- Pull requests required before merging.
- Required CI checks:
  - `lint and test (GitHub Actions)`
  - `build image (GitHub Actions)`
- Force pushes blocked.
- Branch deletion restricted.
- GitHub Secrets configured:
  - `DATABASE_URL`
  - `RENDER_DEPLOY_HOOK`
- Repository variable configured:
  - `LIVE_URL`
- No database credentials or deploy hooks committed to Git.

## 5. UptimeRobot Monitoring

- Monitor name: CycloneReady API.
- Monitoring URL: https://cycloneready.onrender.com/health
- Check interval: Every 5 minutes.
- Status: Up.
- Email alerts enabled.
- Fixed HEAD request support for the health endpoint.
- Verified HTTP HEAD request returns 200 OK.
- Uptime badge configured in README.md.
- Monitor-specific API key is not stored in Git or project files.

## 6. Nightly Production Health Check

- Created `.github/workflows/nightly-health.yml`.
- Scheduled execution: Every day at 12:00 AM IST.
- Added manual execution using `workflow_dispatch`.
- Validates production health endpoint.
- Checks that status is `ok`.
- Checks that environment is `production`.

**Manual test evidence:**

- Workflow: Nightly Health Check #1.
- Status: Success.
- Duration: 7 seconds.
- Commit: `661c669abdff6c901f566cade6934b6ffa1217d6`

Health-check output:

```text
Checking CycloneReady production health...
Health response: {"status":"ok","app":"cycloneready","env":"production","version":"661c669abdff6c901a48649d669b5ea445ab4d3"} # pragma: allowlist secret
CycloneReady is healthy!
```

## 7. Rollback and Roll-forward Drill

**Rollback:**

- Previous version SHA: `7ccdcdb396397081e8f7f70dafff19f769eb1eda`
- Commit: Merge pull request #6.
- Workflow: CD #7.
- Run ID: `44799668244`.
- Deployment status: Success.
- Duration: 50 seconds.
- Live health endpoint verified the older version was running.

**Roll-forward:**

- Latest version SHA: `661c669abdff6c901f566cade6934b6ffa1217d6`
- Workflow: CD #8.
- Run ID: `44800188227`.
- Deployment status: Success.
- Duration: 51 seconds.
- Live health endpoint verified the latest version was restored.

**Database migration safety:**

- Database migrations were skipped during rollback.
- The existing database schema was retained.
- The rollback did not downgrade or delete database schema changes.
- The newer schema changes were additive, so the older application version could continue operating without using the additional column and index.

## 8. Production Deployment Lead Time

Measured lead time from PR merge until the successful production smoke test.

All timestamps below are in Indian Standard Time (IST).

| Deployment | PR | CD run | Merge time (IST) | Smoke-test success time (IST) | Lead time |
|---|---|---|---|---|---|
| 1 | #10 | CD #4 | 20 Nov, 11:17:59 PM | 20 Nov, 11:20:25 PM | 2m 26s |
| 2 | #11 | CD #5 | 20 Nov, 11:59:10 PM | 21 Nov, 12:01:29 AM | 2m 19s |
| 3 | #12 | CD #6 | 21 Nov, 12:16:41 AM | 21 Nov, 12:18:55 AM | 2m 14s |

**Deployment measurements:**

- CD #4 execution duration: 58 seconds.
- CD #5 execution duration: 52 seconds.
- CD #6 execution duration: 58 seconds.
- Average deployment lead time: 2 minutes 20 seconds.
- Slowest CD step: `Smoke test live application`.
- Longest observed smoke-test duration: 35 seconds (CD #6).

## 9. Stretch Tasks

- Dependabot weekly GitHub Actions dependency updates configured.
- Pre-commit checks added to CI.
- Nightly production health check configured.
- Rollback and roll-forward tested successfully.
- Production environment approval gate not enabled because this is a solo automatic deployment workflow; enabling a required reviewer would interrupt unattended deployments.

## 10. Useful Production URLs

- Live application: https://cycloneready.onrender.com
- API documentation: https://cycloneready.onrender.com/docs
- Health check: https://cycloneready.onrender.com/health
- GitHub repository: https://github.com/sudharsank2518/prince28-agr05-cycloneready

## 11. Day 5 Status

- [x] CI workflow configured and verified.
- [x] Main branch protection configured.
- [x] Render production deployment completed.
- [x] Automatic CD verified.
- [x] UptimeRobot monitoring configured and verified.
- [x] CI, Live and Uptime badges added to README.
- [x] Nightly health-check workflow tested successfully.
- [x] Rollback drill completed successfully.
- [x] Roll-forward completed successfully.
- [x] Dependabot weekly updates configured.
- [x] Pre-commit checks integrated into CI.
- [x] Measured lead time across three successful CD runs.
- [x] Identified the slowest CD step.
- [ ] Commit and merge final documentation updates.
- [ ] Create and push the `week-1` Git tag.
- [ ] Share the live URL with the trainer.

**Live Project:** https://cycloneready.onrender.com

---

## 12. Day 6 – Corpus Collection and Stretch Tasks

### 1. Implementation

- [x] Implemented the resumable document downloader using HTTPX.
- [x] Added robots.txt checking and polite crawling controls.
- [x] Added retry handling, concurrency limits and download size limits.
- [x] Added append-only manifest tracking and SHA-256 checksums.
- [x] Added source review and licence tracking.
- [x] Added dataset and capacity report generation.
- [x] Added SHA-256 duplicate detection.
- [x] Implemented ETag-based conditional requests using If-None-Match and HTTP 304 handling.
- [x] Added manifest-based S3-compatible storage uploader.
- [x] Configured local Silo object storage using Docker Compose.
- [x] Verified a sample file upload to local Silo storage.

### 2. Testing and Verification

- [x] Downloader unit tests: 28 passed.
- [x] Full test suite: 42 passed.
- [x] Ruff lint: passed.
- [x] Ruff formatting: passed.
- [x] ETag / HTTP 304 conditional request test: 1 passed.
- [x] Silo uploader dry-run verified; no corpus files available to upload.
- [x] Dataset and capacity reports regenerated; current corpus baseline is 0 files and 0 pages.
- [x] Mocked downloader restart/resume test: passed.
- [x] Interrupted-download cleanup test: passed.
- [x] Cancellation cleanup test: passed.
- [x] Dataset report generated successfully.
- [x] Capacity report generated successfully.
- [x] Docker Compose configuration validated.
- [x] Local API health endpoint verified.
- [x] PostgreSQL and Redis health verified.
- [x] Production deployment verified with the latest main commit.

### 3. Corpus Status

- Documents collected: 0.
- PDF pages collected: 0.
- Extracted tokens: 0.
- Duplicate SHA-256 groups: 0.
- Actual corpus files uploaded to Silo: 0.
- Sample storage upload verified separately.

### 4. Source Review and Permission Requests

Permission requests were sent on 23 November 2026.

| Organisation | Status |
|---|---|
| NDMA | Awaiting response |
| TNSDMA | Awaiting response |
| IMD / RSMC | Awaiting response |

- NDMA robots.txt returned HTTP 403; automated access rules remain unverified.
- TNSDMA SSL certificate verification issue remains unresolved.
- IMD/RSMC robots.txt returned HTTP 404; reproduction permission is still pending.
- No source has yet been approved for automated downloading or reproduction.
- Source decisions are documented in `docs/SOURCE_REVIEW.md`.

### 5. Capacity Report

- Current corpus size: 0 documents and 0 pages.
- Tokens per page: Not yet measurable.
- Embedding cost: Not calculated because no representative corpus has been collected.
- PostgreSQL capacity: Not yet verified against a measured corpus.
- A representative approved document sample is required before reliable capacity estimates can be made.
- The expected effect of a 10x corpus increase is documented in `docs/CAPACITY.md`.

### 6. Remaining Work

- [ ] Obtain source permissions and verify access rules.
- [ ] Collect the approved initial document corpus.
- [x] Perform a real interrupted-download and restart test using a local synthetic HTTP server: Run 1 interrupted with Ctrl+C after the fast file completed; Run 2 skipped the completed file and downloaded the interrupted file; Run 3 skipped both files. Verified manifest entries and SHA-256 hashes.
- [ ] Upload actual corpus documents to local Silo.
- [ ] Measure a representative document sample.
- [ ] Update capacity estimates using measured data.
- [ ] Record final corpus metrics and observations.
- [ ] Verify duplicate detection against actual collected documents.

### 7. Day 6 Status

Downloader implementation, ETag handling, source-review documentation, reporting, duplicate-detection implementation, local object storage setup and automated tests are completed and verified.

The Silo uploader dry-run and code-quality checks have also been verified.

Corpus collection, real-corpus duplicate validation, actual corpus upload and final capacity measurements remain pending because source permissions have not yet been confirmed.

**Day 6 is partially completed; final collection and validation are pending.**
