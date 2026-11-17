# CycloneReady

Helps neighbourhood groups prepare for cyclones and floods using NDMA and Tamil Nadu disaster plans, always pointing to current official alerts.

**Status:** Day 1 foundation (FastAPI skeleton, quality gates). Live URL from Day 5.

## Who it's for

Resident welfare coordinator in a low-lying Chennai neighbourhood preparing families for the northeast monsoon.

## The problem

Guidance is spread across NDMA guidelines, the state plan and IMD warning formats, and people confuse warning stages and colour codes.

## Data sources

NDMA guidelines (cyclones, urban flooding, heat waves), Tamil Nadu State Disaster Management Plan, IMD cyclone warning SOPs and bulletin formats.

- https://ndma.gov.in/
- https://tnsdma.tn.gov.in/
- https://rsmcnewdelhi.imd.gov.in/
- Terms: Public guidelines.

## Hardest problem (my interview story)

Warning stages and safety: answers must map warning stages and colour codes to local actions without giving stale live instructions; every answer about an active event must point to current official alerts.

## Signature feature

Preparedness planner: enter household details and get a checklist by warning stage, in Tamil and English.

## Target metric

Correct stage-to-action mapping for 95%+ of 30 questions; 100% of live-event questions point to official alerts.

## Run it locally

```bash
uv sync
cp .env.example .env   # Windows: copy .env.example .env
uv run uvicorn cycloneready.api.main:create_app --factory --reload
```

Then open http://localhost:8000/docs

## Checks

```bash
uv run pytest
uv run ruff check .
```
