"""Check connectivity to the configured LLM providers."""

import asyncio
import sys

import httpx

from cycloneready.config import get_settings


async def test_provider(
    client: httpx.AsyncClient,
    name: str,
    api_key: str,
    base_url: str,
    model: str,
) -> bool:
    """Send a small request and check whether a provider is reachable."""

    print(f"\nTesting {name}...")
    print(f"Model: {model}")
    print(f"Base URL: {base_url}")

    if not api_key:
        print(f"FAILED: {name} API key is missing.")
        return False

    url = f"{base_url.rstrip('/')}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Reply with exactly: connection successful",
            }
        ],
        "temperature": 0,
        "max_tokens": 30,
    }

    try:
        response = await client.post(
            url,
            headers=headers,
            json=payload,
        )

        print(f"HTTP status: {response.status_code}")

        if response.is_success:
            result = response.json()
            answer = result["choices"][0]["message"]["content"]

            print("SUCCESS: Provider connection working!")
            print("Response:", answer)
            return True

        print(f"FAILED: HTTP {response.status_code}")

        try:
            error_data = response.json()

            if isinstance(error_data, dict):
                error = error_data.get("error", error_data)

                if isinstance(error, dict):
                    message = error.get("message") or str(error)
                else:
                    message = str(error)

                print("Reason:", message)
            else:
                print("Response details:", str(error_data)[:1000])

        except ValueError:
            print("Response details:", response.text[:1000])

        return False

    except httpx.TimeoutException:
        print(f"FAILED: {name} request timed out.")
        return False

    except httpx.HTTPError as exc:
        print(f"FAILED: {name} connection error: {exc}")
        return False

    except (KeyError, IndexError, TypeError, ValueError) as exc:
        print(f"FAILED: Unexpected provider response: {exc}")
        return False


async def main() -> int:
    """Test the configured primary and fallback providers."""

    settings = get_settings()

    providers = [
        (
            "Gemini (primary)",
            settings.gemini_api_key,
            settings.llm_primary_base_url,
            settings.llm_primary_model,
        ),
        (
            "Groq (fallback)",
            settings.groq_api_key,
            settings.llm_fallback_base_url,
            settings.llm_fallback_model,
        ),
    ]

    timeout = httpx.Timeout(settings.llm_timeout_seconds)

    results: list[tuple[str, bool]] = []

    async with httpx.AsyncClient(timeout=timeout) as client:
        for name, api_key, base_url, model in providers:
            passed = await test_provider(
                client=client,
                name=name,
                api_key=api_key,
                base_url=base_url,
                model=model,
            )
            results.append((name, passed))

    print("\n" + "=" * 45)
    print("LLM PROVIDER CONNECTION SUMMARY")
    print("=" * 45)

    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"{name}: {status}")

    all_passed = all(passed for _, passed in results)

    if all_passed:
        print("\nBoth LLM providers are reachable.")
        return 0

    print("\nOne or more LLM provider checks failed.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
