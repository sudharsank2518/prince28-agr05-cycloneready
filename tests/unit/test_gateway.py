"""Tests for the LLM gateway and OpenAI-compatible provider."""

import asyncio

import cycloneready.llm.gateway as gateway_module
from cycloneready.llm.gateway import (
    FakeLLMProvider,
    LLMGateway,
    OpenAICompatibleProvider,
    ProviderResponse,
)

ASK = [{"role": "user", "content": "What is a cyclone warning?"}]


def test_fake_provider_returns_a_response():
    provider = FakeLLMProvider(
        name="test",
        model="test-model",
        response="Stay safe.",
    )

    result = asyncio.run(provider.generate(ASK))

    assert isinstance(result, ProviderResponse)
    assert result.content == "Stay safe."
    assert result.model == "test-model"


def test_gateway_returns_primary_provider_response():
    primary = FakeLLMProvider(
        name="primary",
        model="primary-model",
        response="Primary answer.",
    )
    fallback = FakeLLMProvider(name="fallback")

    gateway = LLMGateway(primary, fallback)

    result = asyncio.run(gateway.generate(ASK))

    assert result.content == "Primary answer."
    assert result.provider == "primary"
    assert result.fallback_used is False


def test_provider_sends_optional_response_format(monkeypatch):
    """The provider sends response_format only when it is supplied."""

    seen_requests = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "model": "test-model",
                "choices": [{"message": {"content": "Test answer."}}],
                "usage": {
                    "prompt_tokens": 9,
                    "completion_tokens": 2,
                },
            }

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            pass

        async def post(self, url, *, headers, json):
            seen_requests.append(
                {
                    "url": url,
                    "headers": headers,
                    "body": json,
                }
            )
            return FakeResponse()

    monkeypatch.setattr(
        gateway_module.httpx,
        "AsyncClient",
        FakeAsyncClient,
    )

    provider = OpenAICompatibleProvider(
        name="test-provider",
        api_key="test-key",  # pragma: allowlist secret
        base_url="https://llm.test/v1",
        model="test-model",
    )

    # First request: response_format is not supplied.
    first = asyncio.run(provider.generate(ASK))

    assert first.content == "Test answer."
    assert "response_format" not in seen_requests[0]["body"]

    # Second request: response_format is supplied.
    expected_format = {"type": "json_object"}

    second = asyncio.run(
        provider.generate(
            ASK,
            response_format=expected_format,
        )
    )

    assert second.content == "Test answer."
    assert seen_requests[1]["body"]["response_format"] == expected_format
    assert seen_requests[1]["body"]["messages"] == ASK
    assert seen_requests[1]["headers"]["Authorization"] == "Bearer test-key"
