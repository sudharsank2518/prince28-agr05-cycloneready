# CycloneReady

Helps neighbourhood groups prepare for cyclones and floods using NDMA and Tamil Nadu disaster plans, always pointing to current official alerts.

[![CI](https://github.com/sudharsank2518/prince28-agr05-cycloneready/actions/workflows/ci.yml/badge.svg)](https://github.com/sudharsank2518/prince28-agr05-cycloneready/actions/workflows/ci.yml)

[![Live](https://img.shields.io/website?url=https%3A%2F%2Fcycloneready.onrender.com%2Fhealth&label=live)](https://cycloneready.onrender.com/docs)

[![Uptime (30 days)](https://img.shields.io/uptimerobot/ratio/m804750005-57078b247c2823d5b862d70c)](https://cycloneready.onrender.com/health)

**Status:** Day 5 — CI/CD deployment and uptime monitoring configured.

**Live application:** https://cycloneready.onrender.com

[API Documentation](https://cycloneready.onrender.com/docs) · [Health Check](https://cycloneready.onrender.com/health)

## Who it's for

Resident welfare coordinator in a low-lying Chennai neighbourhood preparing families for the northeast monsoon.

## The problem

Guidance is spread across NDMA guidelines, the state plan and IMD warning formats, and people confuse warning stages and colour codes.

## Data sources

NDMA guidelines (cyclones, urban flooding, heat waves), Tamil Nadu State Disaster Management Plan, IMD cyclone warning SOPs and bulletin formats.

- [NDMA](https://ndma.gov.in/)
- [Tamil Nadu SDMA](https://tnsdma.tn.gov.in/)
- [RSMC New Delhi – IMD](https://rsmcnewdelhi.imd.gov.in/)
- Terms: Public guidelines. Check individual source permissions before reuse.

## Hardest problem (my interview story)

Warning stages and safety: answers must map warning stages and colour codes to local actions without giving stale live instructions; every answer about an active event must point to current official alerts.

## Signature feature

Preparedness planner: enter household details and get a checklist by warning stage, in Tamil and English.

## Target metric

Correct stage-to-action mapping for 95%+ of 30 questions; 100% of live-event questions point to official alerts.

## Run locally in one command

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

[http://localhost:8000/docs](http://localhost:8000/docs)

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

```powershell
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

## CI/CD and deployment

CycloneReady uses GitHub Actions for continuous integration and deployment.

- CI runs on pull requests and pushes to the main branch.
- Automated checks include linting, tests, and Docker image builds.
- Successful changes merged into `main` trigger deployment to Render.
- A live smoke test verifies the deployed application.
- GitHub repository secrets store deployment credentials and database connection details.

### Live deployment

- **Hosting:** Render
- **Database:** Neon PostgreSQL
- **Container registry:** GitHub Container Registry (GHCR)
- **Deployment URL:** https://cycloneready.onrender.com

### Monitoring

UptimeRobot monitors the `/health` endpoint every 5 minutes to check application availability.
