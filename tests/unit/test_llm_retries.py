"""Tests for LLM provider retry handling and Retry-After parsing."""

import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest

import cycloneready.llm.gateway as gateway_module
from cycloneready.llm.gateway import (
    LLMGateway,
    ProviderError,
    ProviderResponse,
    ProviderStreamEvent,
    parse_retry_after,
)


class SequenceProvider:
    """Provider that returns or raises a sequence of configured results."""

    def __init__(self, results, name="test-provider", model="test-model"):
        self.name = name
        self.model = model
        self.results = list(results)
        self.calls = 0

    async def generate(
        self,
        messages,
        *,
        temperature=0.2,
        max_tokens=1000,
    ):
        self.calls += 1

        result = self.results.pop(0)

        if isinstance(result, Exception):
            raise result

        return result


def successful_response(content="Test response"):
    """Create a successful provider response."""

    return ProviderResponse(
        content=content,
        model="test-model",
        input_tokens=10,
        output_tokens=20,
    )


def test_parse_retry_after_seconds():
    """Retry-After can be supplied as a number of seconds."""

    assert parse_retry_after("2.5") == 2.5
    assert parse_retry_after("0") == 0.0


def test_parse_retry_after_http_date():
    """Retry-After can also be supplied as an HTTP date."""

    future_time = datetime.now(UTC) + timedelta(seconds=30)
    header_value = format_datetime(future_time, usegmt=True)

    delay = parse_retry_after(header_value)

    assert delay is not None
    assert 0 <= delay <= 30


def test_parse_retry_after_invalid_values():
    """Missing or invalid Retry-After values return None."""

    assert parse_retry_after(None) is None
    assert parse_retry_after("") is None
    assert parse_retry_after("not-a-valid-date") is None


def test_retry_after_delay_is_used(monkeypatch):
    """The gateway respects the provider's Retry-After delay."""

    provider = SequenceProvider(
        [
            ProviderError(
                "Rate limited",
                status_code=429,
                retry_after=2.5,
            ),
            successful_response(),
        ]
    )

    gateway = LLMGateway(
        provider,
        SequenceProvider([successful_response()]),
        retry_attempts=2,
        retry_delay_seconds=1,
    )

    delays = []

    async def fake_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(gateway_module.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        gateway._call_with_retries(
            provider,
            [{"role": "user", "content": "Hello"}],
            temperature=0.2,
            max_tokens=100,
        )
    )

    assert result.content == "Test response"
    assert provider.calls == 2
    assert delays == [2.5]


def test_exponential_retry_delay_is_used(monkeypatch):
    """Temporary failures use exponential retry delays."""

    provider = SequenceProvider(
        [
            ProviderError("Server unavailable", status_code=503),
            ProviderError("Server unavailable", status_code=503),
            successful_response(),
        ]
    )

    gateway = LLMGateway(
        provider,
        SequenceProvider([successful_response()]),
        retry_attempts=3,
        retry_delay_seconds=0.25,
    )

    delays = []

    async def fake_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(gateway_module.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        gateway._call_with_retries(
            provider,
            [{"role": "user", "content": "Hello"}],
            temperature=0.2,
            max_tokens=100,
        )
    )

    assert result.content == "Test response"
    assert provider.calls == 3
    assert delays == [0.25, 0.5]


def test_non_retryable_error_stops_immediately(monkeypatch):
    """HTTP 400 errors should not be retried."""

    provider = SequenceProvider(
        [
            ProviderError(
                "Bad request",
                status_code=400,
            ),
            successful_response(),
        ]
    )

    gateway = LLMGateway(
        provider,
        SequenceProvider([successful_response()]),
        retry_attempts=3,
        retry_delay_seconds=0,
    )

    delays = []

    async def fake_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(gateway_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(ProviderError, match="Bad request"):
        asyncio.run(
            gateway._call_with_retries(
                provider,
                [{"role": "user", "content": "Hello"}],
                temperature=0.2,
                max_tokens=100,
            )
        )

    assert provider.calls == 1
    assert delays == []


def test_primary_failure_uses_fallback():
    """A non-retryable primary failure should use the fallback provider."""

    primary = SequenceProvider(
        [
            ProviderError(
                "Primary bad request",
                status_code=400,
            )
        ],
        name="gemini",
        model="gemini-test",
    )

    fallback = SequenceProvider(
        [successful_response("Fallback response")],
        name="groq",
        model="groq-test",
    )

    gateway = LLMGateway(
        primary,
        fallback,
        retry_attempts=3,
        retry_delay_seconds=0,
    )

    result = asyncio.run(gateway.generate([{"role": "user", "content": "Hello"}]))

    assert result.content == "Fallback response"
    assert result.provider == "groq"
    assert result.fallback_used is True
    assert primary.calls == 1
    assert fallback.calls == 1


class SequenceStreamProvider(SequenceProvider):
    """Provider that returns or raises a sequence of streaming results."""

    async def stream(
        self,
        messages,
        *,
        temperature=0.2,
        max_tokens=1000,
    ):
        self.calls += 1
        result = self.results.pop(0)

        if isinstance(result, Exception):
            raise result

        for event in result:
            yield event


def test_stream_retries_before_content(monkeypatch):
    """A failed stream is retried when no content has been received."""

    provider = SequenceStreamProvider(
        [
            ProviderError("Temporary stream failure", status_code=503),
            [ProviderStreamEvent(content="Recovered response")],
        ],
        name="primary",
    )
    fallback = SequenceStreamProvider(
        [[ProviderStreamEvent(content="Fallback response")]],
        name="fallback",
    )
    gateway = LLMGateway(
        provider,
        fallback,
        retry_attempts=2,
        retry_delay_seconds=0,
    )

    async def fake_sleep(delay):
        pass

    monkeypatch.setattr(gateway_module.asyncio, "sleep", fake_sleep)

    async def collect():
        return [event async for event in gateway.stream([{"role": "user", "content": "Hello"}])]

    events = asyncio.run(collect())

    assert provider.calls == 2
    assert fallback.calls == 0
    assert any(event["content"] == "Recovered response" for event in events)
    assert events[-1]["event"] == "done"


def test_stream_uses_fallback_after_primary_failure(monkeypatch):
    """The fallback provider is used after primary stream retries fail."""

    primary = SequenceStreamProvider(
        [
            ProviderError("Primary unavailable", status_code=503),
            ProviderError("Primary unavailable", status_code=503),
        ],
        name="primary",
    )
    fallback = SequenceStreamProvider(
        [[ProviderStreamEvent(content="Fallback response")]],
        name="fallback",
    )
    gateway = LLMGateway(
        primary,
        fallback,
        retry_attempts=2,
        retry_delay_seconds=0,
    )

    async def fake_sleep(delay):
        pass

    monkeypatch.setattr(gateway_module.asyncio, "sleep", fake_sleep)

    async def collect():
        return [event async for event in gateway.stream([{"role": "user", "content": "Hello"}])]

    events = asyncio.run(collect())

    assert primary.calls == 2
    assert fallback.calls == 1
    assert any(event["content"] == "Fallback response" for event in events)
    assert events[-1]["event"] == "done"
    assert events[-1]["fallback_used"] is True


def test_stream_failure_after_partial_content_does_not_use_fallback():
    """A partial response must not be mixed with a fallback response."""

    class PartialFailureProvider:
        name = "primary"
        model = "test-model"

        def __init__(self):
            self.calls = 0

        async def stream(
            self,
            messages,
            *,
            temperature=0.2,
            max_tokens=1000,
        ):
            self.calls += 1
            yield ProviderStreamEvent(content="Partial response")
            raise ProviderError("Connection lost", status_code=503)

    primary = PartialFailureProvider()
    fallback = SequenceStreamProvider(
        [[ProviderStreamEvent(content="Fallback response")]],
        name="fallback",
    )

    gateway = LLMGateway(
        primary,
        fallback,
        retry_attempts=2,
        retry_delay_seconds=0,
    )

    async def collect():
        events = []
        with pytest.raises(ProviderError, match="Connection lost"):
            async for event in gateway.stream([{"role": "user", "content": "Hello"}]):
                events.append(event)
        return events

    events = asyncio.run(collect())

    assert primary.calls == 1
    assert fallback.calls == 0
    assert any(event["content"] == "Partial response" for event in events)
    assert not any(event["content"] == "Fallback response" for event in events)
