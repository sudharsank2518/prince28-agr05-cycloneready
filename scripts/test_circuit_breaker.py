"""Test that the primary circuit breaker opens after repeated failures."""

import asyncio

from cycloneready.llm.gateway import FakeLLMProvider, LLMGateway


async def main():
    primary = FakeLLMProvider(
        name="gemini",
        model="gemini-3.5-flash-lite",
        should_fail=True,
    )

    fallback = FakeLLMProvider(
        name="groq",
        model="openai/gpt-oss-20b",
        response="Fallback working",
    )

    gateway = LLMGateway(
        primary,
        fallback,
        retry_attempts=2,
        retry_delay_seconds=0,
        failure_threshold=3,
    )

    messages = [{"role": "user", "content": "Hello"}]

    print("========== CIRCUIT BREAKER TEST ==========")

    for request_number in range(1, 4):
        result = await gateway.generate(messages)

        print(f"\nRequest {request_number}")
        print("Provider:", result.provider)
        print("Fallback used:", result.fallback_used)
        print("Gemini calls:", primary.calls)
        print("Gemini circuit:", gateway.primary_breaker.state)

    assert gateway.primary_breaker.state == "open"
    assert primary.calls == 6

    print("\nTesting request after circuit opens...")

    previous_gemini_calls = primary.calls
    result = await gateway.generate(messages)

    print("Provider:", result.provider)
    print("Fallback used:", result.fallback_used)
    print("Gemini calls:", primary.calls)
    print("Groq calls:", fallback.calls)
    print("Gemini circuit:", gateway.primary_breaker.state)

    assert primary.calls == previous_gemini_calls
    assert result.provider == "groq"
    assert result.fallback_used is True

    print("\nCIRCUIT BREAKER TEST PASSED!")


if __name__ == "__main__":
    asyncio.run(main())
