"""LLM gateway status endpoints."""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/status")
def llm_status(request: Request) -> dict:
    """Return the current state of configured provider circuit breakers."""

    gateway = request.app.state.llm_gateway

    result = {
        "status": "ok",
        "primary": {
            "provider": gateway.primary.name,
            "model": gateway.primary.model,
            "circuit": gateway.primary_breaker.state,
            "failure_count": gateway.primary_breaker.failure_count,
        },
        "fallback": {
            "provider": gateway.fallback.name,
            "model": gateway.fallback.model,
            "circuit": gateway.fallback_breaker.state,
            "failure_count": gateway.fallback_breaker.failure_count,
        },
    }

    if gateway.tertiary is not None and gateway.tertiary_breaker is not None:
        result["tertiary"] = {
            "provider": gateway.tertiary.name,
            "model": gateway.tertiary.model,
            "circuit": gateway.tertiary_breaker.state,
            "failure_count": gateway.tertiary_breaker.failure_count,
        }

    return result
