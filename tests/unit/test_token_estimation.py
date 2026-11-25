from cycloneready.llm.gateway import (
    LLMGateway,
    ProviderResponse,
    ProviderStreamEvent,
    estimate_messages_tokens,
    estimate_tokens,
)


class MissingUsageProvider:
    """Fake provider that deliberately omits token usage."""

    name = "test-provider"
    model = "gemini-3.5-flash-lite"

    async def generate(self, messages, **kwargs):
        return ProviderResponse(
            content="Stay safe during a cyclone.",
            model=self.model,
        )

    async def stream(self, messages, **kwargs):
        yield ProviderStreamEvent(content="Stay safe ")
        yield ProviderStreamEvent(content="during a cyclone.")


def test_estimate_tokens_for_empty_text():
    assert estimate_tokens("") == 0


def test_estimate_tokens_for_short_text():
    assert estimate_tokens("Hello") == 2


def test_estimate_tokens_rounds_up():
    assert estimate_tokens("123456789") == 3


def test_estimate_messages_tokens():
    messages = [
        {"role": "user", "content": "Hello cyclone"},
        {"role": "assistant", "content": "Stay safe"},
    ]

    result = estimate_messages_tokens(messages)

    assert result > 0


def test_estimate_messages_tokens_for_empty_messages():
    assert estimate_messages_tokens([]) == 0


async def test_gateway_estimates_missing_usage():
    provider = MissingUsageProvider()

    gateway = LLMGateway(
        primary=provider,
        fallback=provider,
        retry_attempts=1,
    )

    messages = [
        {"role": "user", "content": "How do I stay safe?"},
    ]

    result = await gateway.generate(messages)

    assert result.input_tokens == estimate_messages_tokens(messages)
    assert result.output_tokens == estimate_tokens("Stay safe during a cyclone.")
    assert result.cost_inr > 0


async def test_stream_estimates_missing_usage():
    provider = MissingUsageProvider()

    gateway = LLMGateway(
        primary=provider,
        fallback=provider,
        retry_attempts=1,
    )

    messages = [
        {"role": "user", "content": "Explain cyclone safety."},
    ]

    events = [event async for event in gateway.stream(messages)]

    done_event = events[-1]

    assert done_event["event"] == "done"
    assert done_event["input_tokens"] == estimate_messages_tokens(messages)
    assert done_event["output_tokens"] == estimate_tokens("Stay safe during a cyclone.")
    assert done_event["cost_inr"] > 0
