from fastapi import APIRouter, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from cycloneready.api.deps import DbSessionDep, SettingsDep

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: SettingsDep) -> dict[str, str]:
    """Liveness: is the process alive?"""
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "version": settings.git_sha,
    }


@router.head("/health")
def health_head() -> Response:
    """Allow uptime monitors to check liveness using HEAD."""
    return Response(status_code=200)


@router.get("/ready")
async def ready(
    session: DbSessionDep,
    response: Response,
) -> dict:
    """Readiness: can this instance connect to PostgreSQL?"""

    checks = {"database": False}

    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = True
    except (SQLAlchemyError, OSError):
        pass

    ok = all(checks.values())

    if not ok:
        response.status_code = 503

    return {
        "status": "ready" if ok else "not_ready",
        "checks": checks,
    }
