"""Smoke-test the live CycloneReady API after deployment."""

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def check_endpoint(url: str, expected_version: str | None = None) -> bool:
    """Check the main production API endpoints."""

    endpoints = [
        "/health",
        "/ready",
        "/v1/documents?limit=1",
    ]

    success = True

    for endpoint in endpoints:
        full_url = f"{url.rstrip('/')}{endpoint}"

        try:
            request = Request(full_url, headers={"User-Agent": "CycloneReady-Smoke-Test"})

            with urlopen(request, timeout=30) as response:
                status_code = response.status
                body = json.loads(response.read().decode("utf-8"))

            if status_code != 200:
                raise RuntimeError(f"Unexpected HTTP status: {status_code}")

            if endpoint == "/health":
                if body.get("status") != "ok":
                    raise RuntimeError("Health status is not ok")

                if expected_version and body.get("version") != expected_version:
                    raise RuntimeError(
                        f"Version mismatch: expected {expected_version}, "
                        f"received {body.get('version')}"
                    )

            elif endpoint == "/ready":
                if body.get("status") != "ready":
                    raise RuntimeError("Application is not ready")

                if body.get("checks", {}).get("database") is not True:
                    raise RuntimeError("Database readiness check failed")

            print(f"PASS {endpoint} - HTTP {status_code}")

        except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as exc:
            print(f"FAIL {endpoint} - {exc}")
            success = False

    return success


def main() -> int:
    parser = argparse.ArgumentParser(description="CycloneReady production smoke test")
    parser.add_argument("url", help="Base URL of the deployed application")
    parser.add_argument(
        "--expect-version",
        help="Expected Git SHA reported by the health endpoint",
    )

    args = parser.parse_args()

    print(f"Testing CycloneReady at: {args.url}")

    if check_endpoint(args.url, args.expect_version):
        print("\nAll smoke tests passed!")
        return 0

    print("\nSmoke tests failed!")
    return 1


if __name__ == "__main__":
    sys.exit(main())
