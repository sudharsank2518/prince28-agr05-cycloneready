"""HTTP client and orchestration gateway for OpenAI-compatible LLM providers."""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PRICES_USD = {
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "openai/gpt-oss-20b": (0.075, 0.30),
    "openai/gpt-oss-120b": (0.15, 0.60),
}

RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def is_daily_quota_error(message: str) -> bool:
    """Identify provider daily quota exhaustion errors."""
    message = message.lower()
    return any(
        marker in message
        for marker in (
            "tokens per day",
            "token per day",
            "tpd",
            "requests per day",
            "request per day",
        )
    )


class ProviderError(Exception):
    """Raised when an LLM provider request fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
        quota_exhausted: bool = False,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after
        self.quota_exhausted = quota_exhausted


class CircuitOpenError(ProviderError):
    """Raised when a provider's circuit breaker is open."""


@dataclass
class ProviderResponse:
    """Standard response returned by an LLM provider."""

    content: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider: str = "unknown"
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    def __post_init__(self):
        if self.input_tokens is None:
            self.input_tokens = self.prompt_tokens
        if self.output_tokens is None:
            self.output_tokens = self.completion_tokens
        if self.prompt_tokens is None:
            self.prompt_tokens = self.input_tokens
        if self.completion_tokens is None:
            self.completion_tokens = self.output_tokens


@dataclass
class ProviderStreamEvent:
    """One event received from a streaming LLM response."""

    content: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class GatewayResponse:
    """Response returned by the LLM gateway."""

    content: str
    provider: str
    model: str
    request_id: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int = 0
    fallback_used: bool = False
    cost_inr: float = 0.0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    def __post_init__(self):
        if self.input_tokens is None:
            self.input_tokens = self.prompt_tokens
        if self.output_tokens is None:
            self.output_tokens = self.completion_tokens
        if self.prompt_tokens is None:
            self.prompt_tokens = self.input_tokens
        if self.completion_tokens is None:
            self.completion_tokens = self.output_tokens

    @property
    def text(self) -> str:
        """Return response content using the Day 9 classifier interface."""
        return self.content


LLMResult = GatewayResponse


def parse_retry_after(value: str | None) -> float | None:
    """Parse Retry-After as seconds or an HTTP date."""

    if not value:
        return None

    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        pass

    try:
        retry_date = parsedate_to_datetime(value)
        if retry_date.tzinfo is None:
            retry_date = retry_date.replace(tzinfo=UTC)
        return max(0.0, (retry_date - datetime.now(UTC)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def estimate_tokens(text: str) -> int:
    """Estimate tokens using approximately four characters per token."""
    if not text:
        return 0
    return (len(text) + 3) // 4


def estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    """Estimate tokens in a chat message list."""
    total = 0
    for message in messages:
        total += estimate_tokens(message.get("role", ""))
        total += estimate_tokens(message.get("content", ""))
        total += 3
    return total


def cost_inr(
    model: str,
    tokens_in: int,
    tokens_out: int,
    usd_inr: float,
) -> float:
    """Calculate estimated cost in INR using the model price table."""
    price_in, price_out = PRICES_USD.get(model, (0.0, 0.0))
    return round(
        (tokens_in * price_in + tokens_out * price_out) / 1_000_000 * usd_inr,
        6,
    )


def calculate_cost_inr(
    *,
    input_tokens: int | None,
    output_tokens: int | None,
    input_price_per_million: float,
    output_price_per_million: float,
    usd_to_inr: float,
) -> float:
    """Calculate estimated LLM cost in INR."""
    input_cost = ((input_tokens or 0) / 1_000_000) * input_price_per_million
    output_cost = ((output_tokens or 0) / 1_000_000) * output_price_per_million
    return (input_cost + output_cost) * usd_to_inr


class OpenAICompatibleProvider:
    """Send chat requests to Gemini, Groq, Ollama, or another compatible API."""

    def __init__(
        self,
        *,
        name: str,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 30.0,
        require_api_key: bool = True,
    ):
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.require_api_key = require_api_key

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _check_api_key(self) -> None:
        if self.require_api_key and not self.api_key:
            raise ProviderError(f"{self.name} API key is not configured")

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1000,
        response_format: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        """Send messages and return the provider's response."""

        self._check_api_key()
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    headers=self._headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

        except httpx.HTTPStatusError as exc:
            response = exc.response
            error_text = response.text

            raise ProviderError(
                f"{self.name} returned HTTP {response.status_code}: {error_text[:500]}",
                status_code=response.status_code,
                retry_after=parse_retry_after(response.headers.get("Retry-After")),
                quota_exhausted=(response.status_code == 429 and is_daily_quota_error(error_text)),
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderError(f"{self.name} request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name} connection failed: {exc}") from exc
        except ValueError as exc:
            raise ProviderError(f"{self.name} returned invalid JSON") from exc

        try:
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("Response content is not text")

            usage = data.get("usage") or {}
            return ProviderResponse(
                content=content,
                model=data.get("model", self.model),
                provider=self.name,
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.name} returned an unexpected response format") from exc

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1000,
    ):
        """Stream response chunks from an OpenAI-compatible provider."""

        self._check_api_key()
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        try:
            async with (
                httpx.AsyncClient(timeout=self.timeout) as client,
                client.stream(
                    "POST",
                    url,
                    headers=self._headers(),
                    json=payload,
                ) as response,
            ):
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue

                    data_text = line.removeprefix("data:").strip()
                    if data_text == "[DONE]":
                        break

                    try:
                        data = json.loads(data_text)
                    except ValueError as exc:
                        raise ProviderError(f"{self.name} returned invalid streaming JSON") from exc

                    usage = data.get("usage") or {}
                    choices = data.get("choices") or []
                    content = ""
                    if choices:
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content") or ""

                    if not isinstance(content, str):
                        raise ProviderError(f"{self.name} returned invalid streaming content")

                    if content or usage:
                        yield ProviderStreamEvent(
                            content=content,
                            input_tokens=usage.get("prompt_tokens"),
                            output_tokens=usage.get("completion_tokens"),
                        )

        except httpx.HTTPStatusError as exc:
            response = exc.response
            error_text = response.text

            raise ProviderError(
                f"{self.name} returned HTTP {response.status_code}: {error_text[:500]}",
                status_code=response.status_code,
                retry_after=parse_retry_after(response.headers.get("Retry-After")),
                quota_exhausted=(response.status_code == 429 and is_daily_quota_error(error_text)),
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderError(f"{self.name} streaming request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name} streaming connection failed: {exc}") from exc


class FakeLLMProvider:
    """Fake provider for testing without making real API calls."""

    def __init__(
        self,
        *,
        name: str = "fake",
        model: str = "fake-model",
        response: str = "This is a fake LLM response.",
        should_fail: bool = False,
    ):
        self.name = name
        self.model = model
        self.response = response
        self.should_fail = should_fail
        self.calls = 0
        self.response_formats: list[dict[str, Any] | None] = []

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1000,
        response_format: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        self.calls += 1
        self.response_formats.append(response_format)
        if self.should_fail:
            raise ProviderError(f"{self.name} simulated failure")
        return ProviderResponse(
            content=self.response,
            model=self.model,
            provider=self.name,
            input_tokens=10,
            output_tokens=20,
        )

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1000,
    ):
        self.calls += 1
        if self.should_fail:
            raise ProviderError(f"{self.name} simulated failure")

        for start in range(0, len(self.response), 5):
            yield ProviderStreamEvent(content=self.response[start : start + 5])
        yield ProviderStreamEvent(input_tokens=10, output_tokens=20)


class CircuitBreaker:
    """Prevent repeated requests to an unhealthy provider."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = "closed"
        self.opened_at: float | None = None

    def allow_request(self) -> bool:
        if self.state == "closed":
            return True

        if self.state == "open":
            if self.opened_at is not None:
                elapsed = time.monotonic() - self.opened_at
                if elapsed >= self.recovery_timeout:
                    self.state = "half_open"
                    return True
            return False

        return False

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = "closed"
        self.opened_at = None

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.state == "half_open" or self.failure_count >= self.failure_threshold:
            self.state = "open"
            self.opened_at = time.monotonic()


class LLMGateway:
    """Manage primary, fallback, and optional tertiary LLM providers."""

    def __init__(
        self,
        primary: Any,
        fallback: Any,
        *,
        tertiary: Any | None = None,
        retry_attempts: int = 2,
        retry_delay_seconds: float = 1.0,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        usd_to_inr: float = 95.0,
        recorder: Any | None = None,
        max_retries: int | None = None,
        retry_delay: float | None = None,
    ):
        self.primary = primary
        self.fallback = fallback
        self.tertiary = tertiary

        if max_retries is not None:
            retry_attempts = max_retries + 1
        if retry_delay is not None:
            retry_delay_seconds = retry_delay

        self.retry_attempts = max(1, retry_attempts)
        self.retry_delay_seconds = retry_delay_seconds
        self.usd_to_inr = usd_to_inr
        self.recorder = recorder
        self.system_prompt = ""

        providers = [primary, fallback]
        if tertiary is not None:
            providers.append(tertiary)

        self.breakers = {
            provider.name: CircuitBreaker(
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
            for provider in providers
        }
        self.primary_breaker = self.breakers[primary.name]
        self.fallback_breaker = self.breakers[fallback.name]
        self.tertiary_breaker = self.breakers[tertiary.name] if tertiary is not None else None

    async def _record_call(
        self,
        *,
        request_id: str,
        provider: Any,
        status: str,
        latency_ms: int,
        error: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        fallback_used: bool = False,
        model: str | None = None,
        cost: float | None = None,
        purpose: str = "chat",
        prompt_version: str = "v1",
    ) -> None:
        """Record one provider attempt without interrupting the request."""

        if self.recorder is None:
            return

        try:
            await self.recorder(
                request_id=request_id,
                provider=provider.name,
                model=model or provider.model,
                purpose=purpose,
                prompt_version=prompt_version,
                status=status,
                error=error,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                cost_inr=(
                    cost
                    if cost is not None
                    else cost_inr(
                        model or provider.model,
                        input_tokens or 0,
                        output_tokens or 0,
                        self.usd_to_inr,
                    )
                ),
                fallback_used=fallback_used,
            )
        except Exception:
            logger.exception(
                "Unable to record LLM call for provider %s",
                provider.name,
            )

    async def _call_with_retries(
        self,
        provider: Any,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        response_format: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        """Retry temporary provider errors, but not exhausted daily quotas."""

        last_error: ProviderError | None = None

        for attempt in range(self.retry_attempts):
            try:
                if response_format is None:
                    return await provider.generate(
                        messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )

                return await provider.generate(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                )

            except ProviderError as exc:
                last_error = exc

                # A daily quota cannot be fixed by waiting a few seconds.
                if exc.quota_exhausted:
                    raise

                if exc.status_code is not None and exc.status_code not in RETRYABLE_STATUS_CODES:
                    raise

                if attempt < self.retry_attempts - 1:
                    delay = (
                        exc.retry_after
                        if exc.retry_after is not None
                        else self.retry_delay_seconds * (2**attempt)
                    )
                    await asyncio.sleep(delay)

        raise ProviderError(
            f"{provider.name} failed after {self.retry_attempts} attempts: {last_error}",
            status_code=last_error.status_code if last_error else None,
            retry_after=last_error.retry_after if last_error else None,
            quota_exhausted=last_error.quota_exhausted if last_error else False,
        ) from last_error

    def _provider_sequence(self) -> list[tuple[Any, CircuitBreaker, bool]]:
        providers = [
            (self.primary, self.primary_breaker, False),
            (self.fallback, self.fallback_breaker, True),
        ]
        if self.tertiary is not None and self.tertiary_breaker is not None:
            providers.append((self.tertiary, self.tertiary_breaker, True))
        return providers

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1000,
        purpose: str = "chat",
        prompt_version: str = "v1",
        response_format: dict[str, Any] | None = None,
    ) -> GatewayResponse:
        """Try configured providers in priority order."""

        request_id = str(uuid.uuid4())
        start_time = time.perf_counter()
        estimated_input = estimate_messages_tokens(messages)
        errors: list[str] = []
        quota_exhausted = False

        for provider, breaker, fallback_used in self._provider_sequence():
            provider_start = time.perf_counter()

            if not breaker.allow_request():
                errors.append(f"{provider.name} circuit is open")
                continue

            try:
                result = await self._call_with_retries(
                    provider,
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                )
                breaker.record_success()

                input_tokens = (
                    result.input_tokens if result.input_tokens is not None else estimated_input
                )
                output_tokens = (
                    result.output_tokens
                    if result.output_tokens is not None
                    else estimate_tokens(result.content)
                )

                latency_ms = int((time.perf_counter() - start_time) * 1000)
                provider_latency = int((time.perf_counter() - provider_start) * 1000)
                total_cost = cost_inr(
                    result.model,
                    input_tokens,
                    output_tokens,
                    self.usd_to_inr,
                )

                await self._record_call(
                    request_id=request_id,
                    provider=provider,
                    status="success",
                    latency_ms=provider_latency,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    fallback_used=fallback_used,
                    model=result.model,
                    cost=total_cost,
                    purpose=purpose,
                    prompt_version=prompt_version,
                )

                return GatewayResponse(
                    content=result.content,
                    provider=provider.name,
                    model=result.model,
                    request_id=request_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    fallback_used=fallback_used,
                    cost_inr=total_cost,
                )

            except ProviderError as exc:
                breaker.record_failure()
                quota_exhausted = quota_exhausted or exc.quota_exhausted
                errors.append(f"{provider.name}: {exc}")
                provider_latency = int((time.perf_counter() - provider_start) * 1000)

                await self._record_call(
                    request_id=request_id,
                    provider=provider,
                    status="failure",
                    latency_ms=provider_latency,
                    error=str(exc)[:2000],
                    input_tokens=estimated_input,
                    output_tokens=0,
                    fallback_used=fallback_used,
                    purpose=purpose,
                    prompt_version=prompt_version,
                )

        if all(not breaker.allow_request() for _, breaker, _ in self._provider_sequence()):
            raise CircuitOpenError(
                "All configured provider circuits are open. " + "; ".join(errors),
                quota_exhausted=quota_exhausted,
            )

        raise ProviderError(
            "All configured providers failed. " + "; ".join(errors),
            quota_exhausted=quota_exhausted,
        )

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1000,
    ):
        """Stream from providers, falling back if one fails before output."""

        request_id = str(uuid.uuid4())
        start_time = time.perf_counter()
        estimated_input = estimate_messages_tokens(messages)
        errors: list[str] = []
        quota_exhausted = False

        for provider, breaker, fallback_used in self._provider_sequence():
            provider_start = time.perf_counter()

            if not breaker.allow_request():
                errors.append(f"{provider.name} circuit is open")
                continue

            received_content = False
            content_parts: list[str] = []
            input_tokens: int | None = None
            output_tokens: int | None = None

            for attempt in range(self.retry_attempts):
                try:
                    async for event in provider.stream(
                        messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    ):
                        if event.input_tokens is not None:
                            input_tokens = event.input_tokens
                        if event.output_tokens is not None:
                            output_tokens = event.output_tokens
                        if event.content:
                            received_content = True
                            content_parts.append(event.content)

                        yield {
                            "event": "chunk",
                            "content": event.content,
                            "provider": provider.name,
                            "model": provider.model,
                            "request_id": request_id,
                            "input_tokens": event.input_tokens,
                            "output_tokens": event.output_tokens,
                            "latency_ms": int((time.perf_counter() - start_time) * 1000),
                            "fallback_used": fallback_used,
                        }

                    breaker.record_success()
                    complete_content = "".join(content_parts)
                    final_input = input_tokens if input_tokens is not None else estimated_input
                    final_output = (
                        output_tokens
                        if output_tokens is not None
                        else estimate_tokens(complete_content)
                    )
                    total_cost = cost_inr(
                        provider.model,
                        final_input,
                        final_output,
                        self.usd_to_inr,
                    )
                    provider_latency = int((time.perf_counter() - provider_start) * 1000)

                    await self._record_call(
                        request_id=request_id,
                        provider=provider,
                        status="success",
                        latency_ms=provider_latency,
                        input_tokens=final_input,
                        output_tokens=final_output,
                        fallback_used=fallback_used,
                        cost=total_cost,
                    )

                    yield {
                        "event": "done",
                        "content": "",
                        "provider": provider.name,
                        "model": provider.model,
                        "request_id": request_id,
                        "input_tokens": final_input,
                        "output_tokens": final_output,
                        "latency_ms": int((time.perf_counter() - start_time) * 1000),
                        "fallback_used": fallback_used,
                        "cost_inr": total_cost,
                    }
                    return

                except ProviderError as exc:
                    if received_content:
                        breaker.record_failure()
                        await self._record_call(
                            request_id=request_id,
                            provider=provider,
                            status="failure",
                            latency_ms=int((time.perf_counter() - provider_start) * 1000),
                            error=str(exc)[:2000],
                            input_tokens=estimated_input,
                            output_tokens=estimate_tokens("".join(content_parts)),
                            fallback_used=fallback_used,
                        )
                        raise

                    if exc.quota_exhausted:
                        quota_exhausted = True
                        errors.append(f"{provider.name}: {exc}")
                        break

                    if (
                        exc.status_code is not None
                        and exc.status_code not in RETRYABLE_STATUS_CODES
                    ):
                        errors.append(f"{provider.name}: {exc}")
                        break

                    if attempt < self.retry_attempts - 1:
                        delay = (
                            exc.retry_after
                            if exc.retry_after is not None
                            else self.retry_delay_seconds * (2**attempt)
                        )
                        await asyncio.sleep(delay)
                    else:
                        errors.append(f"{provider.name}: {exc}")

            breaker.record_failure()
            last_error = errors[-1] if errors else f"{provider.name} failed"

            await self._record_call(
                request_id=request_id,
                provider=provider,
                status="failure",
                latency_ms=int((time.perf_counter() - provider_start) * 1000),
                error=last_error[:2000],
                input_tokens=estimated_input,
                output_tokens=0,
                fallback_used=fallback_used,
            )

        raise ProviderError(
            "All configured providers failed during streaming. " + "; ".join(errors),
            quota_exhausted=quota_exhausted,
        )
