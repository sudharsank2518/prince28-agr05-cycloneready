"""Test the real LLM gateway using configured providers."""

import asyncio

from cycloneready.config import get_settings
from cycloneready.llm import create_llm_gateway


async def main():
    settings = get_settings()
    gateway = create_llm_gateway(settings)

    print("========== CONFIGURATION ==========")
    print("Primary provider:", gateway.primary.name)
    print("Primary model:", gateway.primary.model)
    print("Fallback provider:", gateway.fallback.name)
    print("Fallback model:", gateway.fallback.model)

    print("\n========== GATEWAY TEST ==========")

    try:
        result = await gateway.generate(
            [{"role": "user", "content": "Reply with: CycloneReady gateway working"}]
        )

        print("Provider:", result.provider)
        print("Model:", result.model)
        print("Response:", result.content)
        print("Input tokens:", result.input_tokens)
        print("Output tokens:", result.output_tokens)
        print("Fallback used:", result.fallback_used)
        print("Cost INR:", result.cost_inr)

    except Exception as exc:
        print("GATEWAY FAILED:", type(exc).__name__, str(exc))


if __name__ == "__main__":
    asyncio.run(main())
