# CycloneReady

Helps neighbourhood groups prepare for cyclones and floods using NDMA and Tamil Nadu disaster plans, always pointing to current official alerts.

**Status:** Day 4 completed — FastAPI backend, PostgreSQL, Redis, Docker Compose, and unit/integration tests. Live URL from Day 5.

## Who it's for

Resident welfare coordinator in a low-lying Chennai neighbourhood preparing families for the northeast monsoon.

## The problem

Guidance is spread across NDMA guidelines, the state plan and IMD warning formats, and people confuse warning stages and colour codes.

## Data sources

NDMA guidelines (cyclones, urban flooding, heat waves), Tamil Nadu State Disaster Management Plan, IMD cyclone warning SOPs and bulletin formats.

- https://ndma.gov.in/
- https://tnsdma.tn.gov.in/
- https://rsmcnewdelhi.imd.gov.in/
- Terms: Public guidelines. Check individual source permissions before reuse.

## Hardest problem (my interview story)

Warning stages and safety: answers must map warning stages and colour codes to local actions without giving stale live instructions; every answer about an active event must point to current official alerts.

## Signature feature

Preparedness planner: enter household details and get a checklist by warning stage, in Tamil and English.

## Target metric

Correct stage-to-action mapping for 95%+ of 30 questions; 100% of live-event questions point to official alerts.

## Run it locally

Install dependencies:

```bash
uv sync
```

Create your environment file:

```powershell
copy .env.example .env
```

Run the FastAPI application:

```bash
uv run poe dev
```

Open the API documentation:

http://localhost:8000/docs

## Run with Docker Compose

Make sure Docker Desktop is running.

Start all services:

```bash
docker compose up --build -d
```

Check service status:

```bash
docker compose ps -a
```

View logs:

```bash
docker compose logs -f
```

Stop services:

```bash
docker compose down
```

### Docker services

| Service | Purpose | Port |
|---|---|---|
| API | FastAPI application | 8000 |
| PostgreSQL | Database with pgvector | 5433 |
| Redis | Cache and supporting service | 6379 |
| Migrate | Database migrations and sample data loading | — |

### Health endpoints

- `/health` — Application liveness check.
- `/ready` — Database readiness check.
- `/docs` — Interactive API documentation.

## Development commands

CycloneReady uses Poe the Poet to manage common development tasks.

| Command | Purpose |
|---|---|
| `uv run poe dev` | Start development server |
| `uv run poe lint` | Run Ruff checks and formatting checks |
| `uv run poe test` | Run unit tests |
| `uv run poe test-integration` | Run PostgreSQL integration tests |
| `uv run poe cov` | Run tests with coverage |
| `uv run poe migrate` | Apply database migrations |
| `uv run poe seed` | Load sample records |

A Makefile is also provided for convenient commands:

```bash
make up
make down
make test
make lint
make cov
make ps
make logs
```

## Testing

Run unit tests:

```bash
uv run poe test
```

Run integration tests with Docker Compose running:

```bash
uv run poe test-integration
```

Run all tests with coverage:

```bash
$env:TEST_DATABASE_URL="postgresql://app:app@localhost:5433/app_test" # pragma: allowlist secret
uv run poe cov
```

Remove the environment variable after testing:

```powershell
Remove-Item Env:TEST_DATABASE_URL
```

## Quality checks

```bash
uv run poe lint
uv run poe cov
```
