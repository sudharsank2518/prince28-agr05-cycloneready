"""Database recorder callback for LLM gateway calls."""

from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from cycloneready.db.llm_calls import LlmCallRepository


def create_llm_recorder(
    sessionmaker: async_sessionmaker,
):
    """Create an async callback that records individual provider calls."""

    async def record_call(
        *,
        request_id: str,
        provider: str,
        model: str,
        status: str,
        latency_ms: int,
        error: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_inr: float = 0.0,
        fallback_used: bool = False,
        purpose: str = "chat",
        prompt_version: str = "v1",
        **kwargs: Any,
    ) -> None:
        async with sessionmaker() as session, session.begin():
            repository = LlmCallRepository(session)

            await repository.record(
                request_id=request_id,
                provider=provider,
                model=model,
                purpose=purpose,
                prompt_version=prompt_version,
                status=status,
                error=error,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                cost_inr=Decimal(str(cost_inr)),
                fallback_used=fallback_used,
            )

    return record_call
