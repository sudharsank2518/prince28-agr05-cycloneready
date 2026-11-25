"""Test automatic fallback using the real Groq provider."""

import asyncio

from cycloneready.config import get_settings
from cycloneready.llm import create_llm_gateway
from cycloneready.llm.gateway import FakeLLMProvider, LLMGateway


async def main():
    settings = get_settings()

    configured_gateway = create_llm_gateway(settings)

    # Simulate Gemini failure.
    failing_primary = FakeLLMProvider(
        name="gemini",
        model=settings.llm_primary_model,
        should_fail=True,
    )

    # Use the actual Groq provider from the application configuration.
    gateway = LLMGateway(
        primary=failing_primary,
        fallback=configured_gateway.fallback,
        retry_attempts=2,
        retry_delay_seconds=0,
        failure_threshold=3,
        usd_to_inr=settings.usd_to_inr,
    )

    print("========== AUTOMATIC FALLBACK TEST ==========")

    try:
        result = await gateway.generate(
            [{"role": "user", "content": "Reply with: Groq fallback working"}]
        )

        print("Provider:", result.provider)
        print("Model:", result.model)
        print("Response:", result.content)
        print("Fallback used:", result.fallback_used)
        print("Gemini simulated calls:", failing_primary.calls)
        print("Gemini circuit:", gateway.primary_breaker.state)
        print("Groq circuit:", gateway.fallback_breaker.state)

        assert result.provider == "groq"
        assert result.fallback_used is True
        assert failing_primary.calls == 2

        print("\nAUTOMATIC FALLBACK TEST PASSED!")

    except Exception as exc:
        print("\nAUTOMATIC FALLBACK TEST FAILED!")
        print(type(exc).__name__, str(exc))


if __name__ == "__main__":
    asyncio.run(main())
