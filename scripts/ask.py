"""Interactive command-line chat using the CycloneReady LLM gateway."""

import asyncio

from cycloneready.config import get_settings
from cycloneready.llm import create_llm_gateway


async def main() -> None:
    settings = get_settings()
    gateway = create_llm_gateway(settings)

    messages = []

    print("=" * 50)
    print("CycloneReady - LLM Chat")
    print("Type 'exit' or 'quit' to stop.")
    print("=" * 50)

    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nChat ended.")
            break

        if question.lower() in {"exit", "quit"}:
            print("Chat ended.")
            break

        if not question:
            continue

        messages.append({"role": "user", "content": question})

        # Keep the six previous messages and the current message.
        conversation = messages[-7:]

        try:
            result = await gateway.generate(conversation)

            print(f"\nCycloneReady: {result.content}")
            print(f"\nProvider: {result.provider}")
            print(f"Model: {result.model}")
            print(f"Input tokens: {result.input_tokens}")
            print(f"Output tokens: {result.output_tokens}")
            print(f"Latency: {result.latency_ms} ms")
            print(f"Cost: Rs. {result.cost_inr:.6f}")
            print(f"Fallback used: {result.fallback_used}")

            messages.append({"role": "assistant", "content": result.content})

        except Exception as exc:
            print(f"\nRequest failed: {type(exc).__name__}: {exc}")
            # Remove the failed question from conversation history.
            messages.pop()


if __name__ == "__main__":
    asyncio.run(main())
