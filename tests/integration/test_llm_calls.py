"""Integration tests for LLM call recording and usage reporting."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from cycloneready.db.llm_calls import LlmCallRepository
from cycloneready.db.session import make_engine, make_sessionmaker


@pytest.fixture
def settings(database_url):
    from cycloneready.config import Settings

    return Settings(app_env="ci", database_url=database_url, _env_file=None)


@pytest.mark.asyncio
async def test_record_llm_call(settings):
    engine = make_engine(settings)

    try:
        async with make_sessionmaker(engine)() as session, session.begin():
            repository = LlmCallRepository(session)

            call = await repository.record(
                request_id="test-request-001",
                provider="groq",
                model="openai/gpt-oss-120b",
                purpose="chat",
                prompt_version="v1",
                status="success",
                latency_ms=250,
                input_tokens=100,
                output_tokens=50,
                cost_inr=Decimal("0.010000"),
                fallback_used=True,
            )

            assert call.request_id == "test-request-001"
            assert call.provider == "groq"
            assert call.model == "openai/gpt-oss-120b"
            assert call.status == "success"
            assert call.fallback_used is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_daily_usage(settings):
    engine = make_engine(settings)

    try:
        async with make_sessionmaker(engine)() as session, session.begin():
            repository = LlmCallRepository(session)

            await repository.record(
                request_id="usage-test-001",
                provider="groq",
                model="openai/gpt-oss-120b",
                purpose="chat",
                prompt_version="v1",
                status="success",
                latency_ms=300,
                input_tokens=120,
                output_tokens=80,
                cost_inr=Decimal("0.020000"),
                fallback_used=True,
            )

            # Match the Asia/Kolkata date used by daily usage reporting.
            india_today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
            usage = await repository.get_daily_usage(india_today)

            assert usage["total_calls"] >= 1
            assert usage["total_input_tokens"] >= 120
            assert usage["total_output_tokens"] >= 80
            assert usage["total_cost_inr"] >= 0.02
            assert usage["fallback_calls"] >= 1
    finally:
        await engine.dispose()
