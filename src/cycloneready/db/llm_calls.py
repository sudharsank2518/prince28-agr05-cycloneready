"""Database operations for recording and reporting LLM usage."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cycloneready.db.models import LlmCall


class LlmCallRepository:
    """Save LLM calls and retrieve daily usage statistics."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(
        self,
        *,
        request_id: str,
        provider: str,
        model: str,
        purpose: str,
        prompt_version: str,
        status: str,
        latency_ms: int,
        error: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_inr: Decimal = Decimal("0"),
        fallback_used: bool = False,
    ) -> LlmCall:
        """Record one LLM request."""

        call = LlmCall(
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
            cost_inr=cost_inr,
            fallback_used=fallback_used,
        )

        self.session.add(call)

        # Flush sends the INSERT without committing the transaction.
        # The caller controls the commit.
        await self.session.flush()

        return call

    async def get_daily_usage(self, day: date) -> dict:
        """Return aggregated LLM usage for a calendar date."""

        database_type = self.session.get_bind().dialect.name

        if database_type == "postgresql":
            # Neon stores timestamps in UTC. Convert to Indian time
            # before extracting the calendar date.
            usage_date = func.timezone(
                "Asia/Kolkata",
                LlmCall.created_at,
            ).cast(Date)
        else:
            # SQLite is used by the unit tests and does not support
            # PostgreSQL's timezone() function.
            usage_date = func.date(LlmCall.created_at)

        statement = select(
            func.count(LlmCall.id).label("total_calls"),
            func.coalesce(func.sum(LlmCall.input_tokens), 0).label("total_input_tokens"),
            func.coalesce(func.sum(LlmCall.output_tokens), 0).label("total_output_tokens"),
            func.coalesce(func.sum(LlmCall.cost_inr), 0).label("total_cost_inr"),
            func.coalesce(func.sum(LlmCall.latency_ms), 0).label("total_latency_ms"),
        ).where(usage_date == day)

        result = await self.session.execute(statement)
        row = result.one()

        fallback_statement = select(func.count(LlmCall.id)).where(
            usage_date == day,
            LlmCall.fallback_used.is_(True),
        )

        fallback_result = await self.session.execute(fallback_statement)

        return {
            "date": day.isoformat(),
            "total_calls": row.total_calls,
            "total_input_tokens": row.total_input_tokens,
            "total_output_tokens": row.total_output_tokens,
            "total_cost_inr": float(row.total_cost_inr),
            "total_latency_ms": row.total_latency_ms,
            "fallback_calls": fallback_result.scalar_one(),
        }
