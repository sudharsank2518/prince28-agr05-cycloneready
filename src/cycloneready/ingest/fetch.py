"""Polite, resumable downloader for the CycloneReady document corpus."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import random
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from protego import Protego

USER_AGENT = (
    "examate-student-bot/0.1 "
    "(student project; "
    "+https://github.com/sudharsank2518/prince28-agr05-cycloneready)"
)

RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}
MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_ATTEMPTS = 4
MAX_CONCURRENCY = 4


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def load_sources(csv_path: Path) -> list[dict]:
    """Read and validate the source register."""
    records = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"url", "source", "licence", "title"}

        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"CSV must contain these columns: {sorted(required)}")

        for line_number, row in enumerate(reader, start=2):
            url = (row.get("url") or "").strip()
            source = (row.get("source") or "").strip()
            licence = (row.get("licence") or "").strip()
            title = (row.get("title") or "").strip()

            if not all((url, source, licence, title)):
                raise ValueError(
                    f"Row {line_number}: URL, source, licence and title are all required."
                )

            if urlparse(url).scheme not in {"http", "https"}:
                raise ValueError(f"Row {line_number}: invalid HTTP(S) URL.")

            blocked_terms = (
                "unclear",
                "unknown",
                "not reviewed",
                "do not fetch",
                "permission required",
                "not permitted",
            )

            if any(term in licence.lower() for term in blocked_terms):
                raise ValueError(f"Row {line_number}: licence/terms need review before fetching.")

            records.append(
                {
                    "url": url,
                    "source": source,
                    "licence": licence,
                    "title": title,
                }
            )

    return records


class Fetcher:
    """Downloads approved URLs while respecting robots.txt and site delays."""

    def __init__(
        self,
        raw_dir: Path = Path("data/raw"),
        manifest_path: Path = Path("data/manifest.jsonl"),
        delay: float = 0.5,
        max_concurrency: int = MAX_CONCURRENCY,
        transport: httpx.AsyncBaseTransport | None = None,
        refresh: bool = False,
    ):
        if max_concurrency < 1 or max_concurrency > MAX_CONCURRENCY:
            raise ValueError("Concurrency must be between 1 and 4.")

        if delay < 0:
            raise ValueError("Delay cannot be negative.")

        self.raw_dir = Path(raw_dir)
        self.manifest_path = Path(manifest_path)
        self.delay = delay
        self.refresh = refresh

        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.transport = transport

        self.robots_cache: dict[str, Protego | None] = {}
        self.host_locks: dict[str, asyncio.Lock] = {}
        self.last_request: dict[str, float] = {}
        self.latest: dict[str, dict] = {}

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

        self._load_manifest()

        self.client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
            transport=transport,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    def _load_manifest(self) -> None:
        """Load the latest manifest entry for each URL."""
        if not self.manifest_path.exists():
            return

        with self.manifest_path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue

                try:
                    item = json.loads(line)

                    if item.get("url"):
                        self.latest[item["url"]] = item

                except json.JSONDecodeError:
                    continue

    def _record(self, item: dict) -> None:
        """Append a manifest record; never rewrite earlier history."""
        item["recorded_at"] = utc_now()

        with self.manifest_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")

        self.latest[item["url"]] = item

    async def _polite_wait(
        self,
        host: str,
        extra_delay: float = 0,
    ) -> None:
        """Separate requests to the same host by the required delay."""
        lock = self.host_locks.setdefault(host, asyncio.Lock())

        async with lock:
            loop = asyncio.get_running_loop()
            now = loop.time()

            required = max(self.delay, extra_delay)
            previous = self.last_request.get(host, 0.0)
            wait = required - (now - previous)

            if wait > 0:
                await asyncio.sleep(wait)

            self.last_request[host] = loop.time()

    async def _robots_allowed(self, url: str) -> tuple[bool, float]:
        """Fail closed when robots.txt cannot be checked."""
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = f"{base}/robots.txt"

        if base not in self.robots_cache:
            try:
                response = await self.client.get(robots_url)

                if response.status_code == 404:
                    self.robots_cache[base] = Protego.parse("")

                elif response.status_code >= 400:
                    self.robots_cache[base] = None

                else:
                    self.robots_cache[base] = Protego.parse(response.text)

            except httpx.HTTPError:
                self.robots_cache[base] = None

        parser = self.robots_cache[base]

        if parser is None:
            return False, 0.0

        allowed = parser.can_fetch(url, USER_AGENT)
        crawl_delay = parser.crawl_delay(USER_AGENT) or 0.0

        return allowed, float(crawl_delay)

    @staticmethod
    def _retry_after(value: str | None) -> float | None:
        """Parse Retry-After as seconds or an HTTP date."""
        if not value:
            return None

        try:
            return min(120.0, max(0.0, float(value)))

        except ValueError:
            try:
                retry_date = parsedate_to_datetime(value)

                seconds = (retry_date - datetime.now(UTC)).total_seconds()

                return min(120.0, max(0.0, seconds))

            except (TypeError, ValueError, OverflowError):
                return None

    @staticmethod
    def _file_name(url: str) -> str:
        """Create a stable, collision-resistant filename from the URL."""
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        suffix = Path(urlparse(url).path).suffix.lower()

        if not suffix or len(suffix) > 10:
            suffix = ".bin"

        return f"{digest}{suffix}"

    def _already_downloaded(self, url: str) -> bool:
        """Check whether a complete local file already exists."""
        item = self.latest.get(url, {})

        if item.get("status") not in {
            "downloaded",
            "not_modified",
        }:
            return False

        path = item.get("file_path")

        return bool(path and Path(path).is_file())

    async def fetch_one(self, source: dict) -> dict:
        """Download one approved source, or safely skip it."""
        url = source["url"]
        started_at = time.perf_counter()
        host = urlparse(url).netloc

        previous = self.latest.get(url, {})

        # Normal mode: skip completed downloads.
        # Refresh mode: check whether the server has changed the file.
        if not self.refresh and self._already_downloaded(url):
            return {
                "url": url,
                "result": "skipped",
            }

        allowed, crawl_delay = await self._robots_allowed(url)

        if not allowed:
            result = {
                **source,
                "status": "blocked",
                "reason": ("robots.txt disallows fetching or could not be checked"),
                "duration_seconds": round(time.perf_counter() - started_at, 3),
            }

            self._record(result)

            return {
                "url": url,
                "result": "blocked",
            }

        filename = self._file_name(url)
        final_path = self.raw_dir / filename
        temp_path = final_path.with_suffix(final_path.suffix + ".part")

        headers = {}

        # ETag stretch feature.
        if self.refresh and previous.get("etag") and self._already_downloaded(url):
            headers["If-None-Match"] = previous["etag"]

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                async with self.semaphore:
                    await self._polite_wait(host, crawl_delay)

                    async with self.client.stream(
                        "GET",
                        url,
                        headers=headers,
                    ) as response:
                        # Server says the local copy is still current.
                        if response.status_code == 304:
                            if not self._already_downloaded(url):
                                raise RuntimeError(
                                    "Received 304 but no complete local file exists."
                                )

                            result = {
                                **source,
                                "status": "not_modified",
                                "file_path": previous.get("file_path"),
                                "etag": previous.get("etag"),
                                "sha256": previous.get("sha256"),
                                "bytes": previous.get("bytes"),
                                "http_status": 304,
                                "attempts": attempt,
                                "duration_seconds": round(time.perf_counter() - started_at, 3),
                            }

                            self._record(result)

                            return {
                                "url": url,
                                "result": "not_modified",
                            }

                        if response.status_code in RETRY_STATUSES:
                            wait = self._retry_after(response.headers.get("Retry-After"))

                            raise RetryableResponse(
                                response.status_code,
                                wait,
                            )

                        response.raise_for_status()

                        content_length = response.headers.get("Content-Length")

                        if content_length and int(content_length) > MAX_FILE_BYTES:
                            raise ValueError("File exceeds the 200 MB limit.")

                        digest = hashlib.sha256()
                        total_bytes = 0

                        try:
                            with temp_path.open("wb") as file:
                                async for chunk in response.aiter_bytes():
                                    total_bytes += len(chunk)

                                    if total_bytes > MAX_FILE_BYTES:
                                        raise ValueError("File exceeds the 200 MB limit.")

                                    digest.update(chunk)
                                    file.write(chunk)

                            # Replace only after a complete download.
                            temp_path.replace(final_path)

                        except Exception:
                            temp_path.unlink(missing_ok=True)
                            raise

                        result = {
                            **source,
                            "status": "downloaded",
                            "file_path": str(final_path).replace(
                                "\\",
                                "/",
                            ),
                            "sha256": digest.hexdigest(),
                            "bytes": total_bytes,
                            "content_type": response.headers.get("Content-Type"),
                            "http_status": response.status_code,
                            "etag": response.headers.get("ETag"),
                            "attempts": attempt,
                            "duration_seconds": round(time.perf_counter() - started_at, 3),
                        }

                        self._record(result)

                        return {
                            "url": url,
                            "result": "downloaded",
                        }

            except RetryableResponse as error:
                if attempt == MAX_ATTEMPTS:
                    break

                wait = error.retry_after

                if wait is None:
                    wait = min(
                        120.0,
                        (2 ** (attempt - 1)) + random.random(),
                    )

                await asyncio.sleep(wait)

            except (
                httpx.TimeoutException,
                httpx.NetworkError,
            ):
                if attempt == MAX_ATTEMPTS:
                    break

                wait = min(
                    120.0,
                    (2 ** (attempt - 1)) + random.random(),
                )

                await asyncio.sleep(wait)

            except Exception as error:
                temp_path.unlink(missing_ok=True)

                result = {
                    **source,
                    "status": "failed",
                    "reason": str(error),
                    "attempts": attempt,
                    "duration_seconds": round(time.perf_counter() - started_at, 3),
                }

                self._record(result)

                return {
                    "url": url,
                    "result": "failed",
                    "reason": str(error),
                }

        temp_path.unlink(missing_ok=True)

        result = {
            **source,
            "status": "failed",
            "reason": "Retry limit reached",
            "attempts": MAX_ATTEMPTS,
            "duration_seconds": round(time.perf_counter() - started_at, 3),
        }

        self._record(result)

        return {
            "url": url,
            "result": "failed",
        }


class RetryableResponse(Exception):
    """Represents an HTTP response that should be retried."""

    def __init__(
        self,
        status_code: int,
        retry_after: float | None,
    ):
        self.status_code = status_code
        self.retry_after = retry_after

        super().__init__(f"Retryable HTTP status: {status_code}")


async def fetch_sources(
    sources: list[dict],
    raw_dir: Path = Path("data/raw"),
    manifest_path: Path = Path("data/manifest.jsonl"),
    delay: float = 0.5,
    max_concurrency: int = MAX_CONCURRENCY,
    refresh: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[dict]:
    """Fetch a list of approved sources."""
    async with Fetcher(
        raw_dir=raw_dir,
        manifest_path=manifest_path,
        delay=delay,
        max_concurrency=max_concurrency,
        refresh=refresh,
        transport=transport,
    ) as fetcher:
        tasks = [fetcher.fetch_one(source) for source in sources]

        return await asyncio.gather(*tasks)


def register_manual_file(
    file_path: Path,
    source: str,
    licence: str,
    title: str,
    original_url: str,
    manifest_path: Path = Path("data/manifest.jsonl"),
) -> dict:
    """Register a manually downloaded file without making a web request."""
    file_path = Path(file_path)

    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not all((source.strip(), licence.strip(), title.strip())):
        raise ValueError("Source, licence and title are required.")

    if urlparse(original_url).scheme not in {"http", "https"}:
        raise ValueError("Original URL must be HTTP(S).")

    if len(licence.strip()) == 0:
        raise ValueError("Licence information is required.")

    digest = hashlib.sha256(file_path.read_bytes()).hexdigest()

    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "url": original_url,
        "source": source,
        "licence": licence,
        "title": title,
        "status": "downloaded",
        "file_path": str(file_path.resolve()).replace("\\", "/"),
        "sha256": digest,
        "bytes": file_path.stat().st_size,
        "content_type": None,
        "http_status": None,
        "etag": None,
        "attempts": 0,
        "method": "manual",
        "recorded_at": utc_now(),
    }

    with manifest_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


async def discover_sitemap_urls(
    sitemap_url: str,
    *,
    include: str = "",
    limit: int = 300,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[str]:
    """Discover URLs from a sitemap without downloading the documents."""

    if urlparse(sitemap_url).scheme not in {"http", "https"}:
        raise ValueError("Sitemap URL must use HTTP or HTTPS.")

    if limit < 1:
        raise ValueError("Sitemap limit must be at least 1.")

    headers = {"User-Agent": USER_AGENT}
    timeout = httpx.Timeout(20.0)

    async with httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        transport=transport,
        follow_redirects=True,
    ) as client:
        parsed = urlparse(sitemap_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        try:
            robots_response = await client.get(robots_url)

            if robots_response.status_code == 404:
                robots = Protego.parse("")
            elif robots_response.status_code >= 400:
                raise PermissionError(
                    f"Cannot verify robots.txt: HTTP {robots_response.status_code}"
                )
            else:
                robots = Protego.parse(robots_response.text)

        except httpx.HTTPError as error:
            raise PermissionError("Cannot verify robots.txt; sitemap access blocked.") from error

        if not robots.can_fetch(sitemap_url, USER_AGENT):
            raise PermissionError("robots.txt does not allow access to this sitemap.")

        response = await client.get(sitemap_url)
        response.raise_for_status()

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as error:
            raise ValueError("Invalid sitemap XML.") from error

        namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        discovered = []

        for element in root.findall(".//sm:url/sm:loc", namespace):
            url = (element.text or "").strip()

            if not url:
                continue

            if urlparse(url).scheme not in {"http", "https"}:
                continue

            if include and include not in url:
                continue

            if url not in discovered:
                discovered.append(url)

            if len(discovered) >= limit:
                break

        return discovered


def append_urls_to_sources_csv(
    urls: list[str],
    *,
    source: str,
    licence: str,
    title: str,
    csv_path: Path = Path("data/sources.csv"),
) -> int:
    """Append new sitemap URLs to sources.csv without duplicates."""

    if not all(isinstance(value, str) and value.strip() for value in (source, licence, title)):
        raise ValueError("Source, licence and title are required.")

    if any(
        word in licence.lower()
        for word in ("unclear", "unknown", "permission required", "not permitted")
    ):
        raise ValueError("A verified licence or permission is required.")

    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    existing = set()

    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8", newline="") as file:
            existing = {row["url"] for row in csv.DictReader(file) if row.get("url")}

    new_urls = []

    for url in urls:
        if urlparse(url).scheme not in {"http", "https"}:
            continue

        if url not in existing:
            new_urls.append(url)
            existing.add(url)

    file_exists = csv_path.exists() and csv_path.stat().st_size > 0

    with csv_path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["url", "source", "licence", "title"],
        )

        if not file_exists:
            writer.writeheader()

        for url in new_urls:
            writer.writerow(
                {
                    "url": url,
                    "source": source,
                    "licence": licence,
                    "title": title,
                }
            )

    return len(new_urls)
