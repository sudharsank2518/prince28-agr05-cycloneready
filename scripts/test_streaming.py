import asyncio

from cycloneready.llm.gateway import (
    FakeLLMProvider,
    LLMGateway,
)


async def main():
    messages = [{"role": "user", "content": "Hello"}]

    print("TEST 1: Primary streaming")

    primary = FakeLLMProvider(
        name="gemini",
        response="Hello from Gemini!",
    )

    fallback = FakeLLMProvider(
        name="groq",
        response="Hello from Groq!",
    )

    gateway = LLMGateway(primary, fallback)

    received = ""

    async for event in gateway.stream(messages):
        received += event["content"]

    print("Response:", received)
    print("Primary calls:", primary.calls)
    print("Fallback calls:", fallback.calls)

    assert received == "Hello from Gemini!"
    assert primary.calls == 1
    assert fallback.calls == 0

    print("\nTEST 2: Fallback streaming")

    primary = FakeLLMProvider(
        name="gemini",
        should_fail=True,
    )

    fallback = FakeLLMProvider(
        name="groq",
        response="Hello from Groq!",
    )

    gateway = LLMGateway(
        primary,
        fallback,
        retry_attempts=2,
        retry_delay_seconds=0,
    )

    received = ""

    async for event in gateway.stream(messages):
        received += event["content"]

    print("Response:", received)
    print("Primary calls:", primary.calls)
    print("Fallback calls:", fallback.calls)

    assert received == "Hello from Groq!"
    assert primary.calls == 2
    assert fallback.calls == 1

    print("\nBoth streaming tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
