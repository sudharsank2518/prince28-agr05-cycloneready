"""LLM package: provider configuration and gateway creation."""

from typing import Any

from cycloneready.config import Settings
from cycloneready.llm.gateway import LLMGateway, OpenAICompatibleProvider


def create_llm_gateway(
    settings: Settings,
    recorder: Any | None = None,
) -> LLMGateway:
    """Create Gemini and Groq providers with optional local Ollama fallback."""

    primary = OpenAICompatibleProvider(
        name="gemini",
        api_key=settings.gemini_api_key,
        base_url=settings.llm_primary_base_url,
        model=settings.llm_primary_model,
        timeout=settings.llm_timeout_seconds,
    )

    fallback = OpenAICompatibleProvider(
        name="groq",
        api_key=settings.groq_api_key,
        base_url=settings.llm_fallback_base_url,
        model=settings.llm_fallback_model,
        timeout=settings.llm_timeout_seconds,
    )

    tertiary = None
    if settings.ollama_enabled:
        tertiary = OpenAICompatibleProvider(
            name="ollama",
            api_key="",
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout=settings.llm_timeout_seconds,
            require_api_key=False,
        )

    return LLMGateway(
        primary=primary,
        fallback=fallback,
        tertiary=tertiary,
        retry_attempts=2,
        retry_delay_seconds=1.0,
        usd_to_inr=settings.usd_to_inr,
        recorder=recorder,
    )


__all__ = ["LLMGateway", "create_llm_gateway"]
