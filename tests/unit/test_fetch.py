import asyncio
import csv
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from cycloneready.ingest.fetch import (
    Fetcher,
    discover_sitemap_urls,
    fetch_sources,
    load_sources,
    register_manual_file,
)


def make_source(url="https://example.com/guide.pdf"):
    return {
        "url": url,
        "source": "Example",
        "licence": "Official public guidelines; terms reviewed",
        "title": "Example guide",
    }


def make_transport(handler):
    return httpx.MockTransport(handler)


def run_fetch(source, tmp_path, handler, **kwargs):
    return asyncio.run(
        fetch_sources(
            [source],
            raw_dir=tmp_path / "raw",
            manifest_path=tmp_path / "manifest.jsonl",
            transport=make_transport(handler),
            delay=0,
            **kwargs,
        )
    )


def read_manifest(path):
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def robots_404_or_file(request):
    if request.url.path == "/robots.txt":
        return httpx.Response(404)
    return httpx.Response(200, content=b"PDF test content")


# 1. Valid source CSV loads correctly
def test_load_sources_valid_csv(tmp_path):
    csv_path = tmp_path / "sources.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["url", "source", "licence", "title"])
        writer.writeheader()
        writer.writerow(make_source())

    sources = load_sources(csv_path)

    assert len(sources) == 1
    assert sources[0]["source"] == "Example"


# 2. Missing CSV header is rejected
def test_load_sources_missing_header(tmp_path):
    csv_path = tmp_path / "sources.csv"
    csv_path.write_text("url,title\n", encoding="utf-8")

    with pytest.raises(ValueError):
        load_sources(csv_path)


# 3. Missing licence is rejected
def test_load_sources_missing_licence(tmp_path):
    csv_path = tmp_path / "sources.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["url", "source", "licence", "title"])
        writer.writeheader()
        writer.writerow(
            {
                "url": "https://example.com/file.pdf",
                "source": "Example",
                "licence": "",
                "title": "Guide",
            }
        )

    with pytest.raises(ValueError):
        load_sources(csv_path)


# 4. Invalid URL scheme is rejected
def test_load_sources_invalid_url(tmp_path):
    csv_path = tmp_path / "sources.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["url", "source", "licence", "title"])
        writer.writeheader()
        writer.writerow(
            {
                **make_source(),
                "url": "ftp://example.com/file.pdf",
            }
        )

    with pytest.raises(ValueError):
        load_sources(csv_path)


# 5. Unverified licence is rejected
def test_load_sources_unverified_licence(tmp_path):
    csv_path = tmp_path / "sources.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["url", "source", "licence", "title"])
        writer.writeheader()
        writer.writerow(
            {
                **make_source(),
                "licence": "Terms unclear - do not fetch",
            }
        )

    with pytest.raises(ValueError):
        load_sources(csv_path)


# 6. robots.txt 404 allows downloading
def test_robots_404_allows_download(tmp_path):
    results = run_fetch(make_source(), tmp_path, robots_404_or_file)
    assert results[0]["result"] == "downloaded"


# 7. robots.txt disallow blocks downloading
def test_robots_disallow_blocks_download(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        return httpx.Response(200, content=b"Should not download")

    results = run_fetch(make_source(), tmp_path, handler)
    assert results[0]["result"] == "blocked"


# 8. robots.txt 403 blocks downloading
def test_robots_403_blocks_download(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(403)
        return httpx.Response(200, content=b"Should not download")

    results = run_fetch(make_source(), tmp_path, handler)
    assert results[0]["result"] == "blocked"


# 9. robots.txt network failure blocks downloading
def test_robots_network_error_blocks_download(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            raise httpx.ConnectError("Connection failed")
        return httpx.Response(200, content=b"Should not download")

    results = run_fetch(make_source(), tmp_path, handler)
    assert results[0]["result"] == "blocked"


# 10. Successful download saves file and checksum
def test_successful_download_and_checksum(tmp_path):
    content = b"Sample cyclone guideline"

    results = run_fetch(
        make_source(),
        tmp_path,
        lambda request: (
            httpx.Response(404)
            if request.url.path == "/robots.txt"
            else httpx.Response(200, content=content)
        ),
    )

    assert results[0]["result"] == "downloaded"

    entries = read_manifest(tmp_path / "manifest.jsonl")
    assert len(entries) == 1
    assert entries[0]["sha256"] == hashlib.sha256(content).hexdigest()

    saved_file = Path(entries[0]["file_path"])
    assert saved_file.exists()
    assert saved_file.read_bytes() == content


# 11. Existing downloaded file is skipped on rerun
def test_existing_download_is_skipped(tmp_path):
    calls = {"download": 0}

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        calls["download"] += 1
        return httpx.Response(200, content=b"Guide")

    source = make_source()
    manifest = tmp_path / "manifest.jsonl"
    raw = tmp_path / "raw"

    asyncio.run(
        fetch_sources(
            [source],
            raw_dir=raw,
            manifest_path=manifest,
            transport=make_transport(handler),
            delay=0,
        )
    )

    first_count = calls["download"]

    results = asyncio.run(
        fetch_sources(
            [source],
            raw_dir=raw,
            manifest_path=manifest,
            transport=make_transport(handler),
            delay=0,
        )
    )

    assert calls["download"] == first_count
    assert results[0]["result"] == "skipped"


# 12. Refresh sends ETag and handles HTTP 304
def test_refresh_handles_not_modified(tmp_path):
    source = make_source()
    manifest = tmp_path / "manifest.jsonl"
    raw = tmp_path / "raw"

    def first_handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200,
            content=b"Original guide",
            headers={"ETag": '"version-1"'},
        )

    asyncio.run(
        fetch_sources(
            [source],
            raw_dir=raw,
            manifest_path=manifest,
            transport=make_transport(first_handler),
            delay=0,
        )
    )

    def refresh_handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        assert request.headers.get("If-None-Match") == '"version-1"'
        return httpx.Response(304)

    results = asyncio.run(
        fetch_sources(
            [source],
            raw_dir=raw,
            manifest_path=manifest,
            transport=make_transport(refresh_handler),
            delay=0,
            refresh=True,
        )
    )

    assert results[0]["result"] == "not_modified"


# 13. Refresh downloads changed content
def test_refresh_updates_changed_content(tmp_path):
    source = make_source()
    manifest = tmp_path / "manifest.jsonl"
    raw = tmp_path / "raw"

    def first_handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200,
            content=b"Old content",
            headers={"ETag": '"old"'},
        )

    asyncio.run(
        fetch_sources(
            [source],
            raw_dir=raw,
            manifest_path=manifest,
            transport=make_transport(first_handler),
            delay=0,
        )
    )

    def refresh_handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200,
            content=b"Updated content",
            headers={"ETag": '"new"'},
        )

    results = asyncio.run(
        fetch_sources(
            [source],
            raw_dir=raw,
            manifest_path=manifest,
            transport=make_transport(refresh_handler),
            delay=0,
            refresh=True,
        )
    )

    assert results[0]["result"] == "downloaded"


# 14. Retryable 503 error retries and succeeds
def test_retryable_503_retries(tmp_path, monkeypatch):
    calls = {"count": 0}

    async def no_sleep(_seconds):
        pass

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)

        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, content=b"Recovered")

    results = run_fetch(make_source(), tmp_path, handler)
    assert results[0]["result"] == "downloaded"
    assert calls["count"] == 2


# 15. Retry-After header is respected
def test_retry_after_header_is_respected(tmp_path, monkeypatch):
    waits = []
    calls = {"count": 0}

    async def record_sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", record_sleep)

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)

        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, headers={"Retry-After": "2"})
        return httpx.Response(200, content=b"Success")

    results = run_fetch(make_source(), tmp_path, handler)
    assert results[0]["result"] == "downloaded"
    assert 2.0 in waits


# 16. Non-retryable HTTP error does not retry
def test_non_retryable_error_does_not_retry(tmp_path, monkeypatch):
    calls = {"count": 0}

    async def no_sleep(_seconds):
        pass

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        calls["count"] += 1
        return httpx.Response(404)

    results = run_fetch(make_source(), tmp_path, handler)
    assert results[0]["result"] == "failed"
    assert calls["count"] == 1


# 17. Interrupted download does not leave partial files
def test_interrupted_download_removes_partial_file(tmp_path, monkeypatch):
    async def no_sleep(_seconds):
        pass

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    class BrokenStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"Partial content"
            raise httpx.ReadError("Connection interrupted")

        async def aclose(self):
            pass

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, stream=BrokenStream())

    results = run_fetch(make_source(), tmp_path, handler)

    assert results[0]["result"] == "failed"
    assert not list((tmp_path / "raw").glob("*.part"))
    assert not list((tmp_path / "raw").glob("*"))


# 18. Files larger than 200 MB are rejected
def test_file_size_limit_rejects_large_file(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"Content-Length": str(201 * 1024 * 1024)},
            content=b"",
        )

    results = run_fetch(make_source(), tmp_path, handler)
    assert results[0]["result"] == "failed"


# 19. Concurrent downloads stay within the configured limit
def test_concurrency_limit_is_respected(tmp_path):
    active = 0
    peak = 0

    async def handler(request):
        nonlocal active, peak

        if request.url.path == "/robots.txt":
            return httpx.Response(404)

        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1

        return httpx.Response(200, content=b"Test document")

    async def run():
        sources = [make_source(f"https://example.com/file-{i}.pdf") for i in range(6)]

        return await fetch_sources(
            sources,
            raw_dir=tmp_path / "raw",
            manifest_path=tmp_path / "manifest.jsonl",
            transport=make_transport(handler),
            delay=0,
            max_concurrency=2,
        )

    results = asyncio.run(run())
    assert all(item["result"] == "downloaded" for item in results)
    assert peak <= 2


# 20. Manual registration creates manifest and checksum
def test_manual_registration_creates_manifest(tmp_path):
    file_path = tmp_path / "guide.pdf"
    content = b"Sample cyclone preparedness guide"
    file_path.write_bytes(content)

    manifest_path = tmp_path / "manifest.jsonl"

    result = register_manual_file(
        file_path=file_path,
        source="NDMA",
        licence="Permission granted for project use",
        title="Cyclone Guide",
        original_url="https://example.com/guide.pdf",
        manifest_path=manifest_path,
    )

    assert result["status"] == "downloaded"
    assert result["method"] == "manual"
    assert result["sha256"] == hashlib.sha256(content).hexdigest()

    entries = read_manifest(manifest_path)
    assert len(entries) == 1
    assert entries[0]["title"] == "Cyclone Guide"


# 21. Manual registration rejects missing file
def test_manual_registration_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        register_manual_file(
            file_path=tmp_path / "missing.pdf",
            source="NDMA",
            licence="Permission granted",
            title="Cyclone Guide",
            original_url="https://example.com/guide.pdf",
            manifest_path=tmp_path / "manifest.jsonl",
        )


# 22. Manual registration rejects missing licence
def test_manual_registration_rejects_missing_licence(tmp_path):
    file_path = tmp_path / "guide.pdf"
    file_path.write_bytes(b"Sample content")

    with pytest.raises(ValueError):
        register_manual_file(
            file_path=file_path,
            source="NDMA",
            licence="",
            title="Cyclone Guide",
            original_url="https://example.com/guide.pdf",
            manifest_path=tmp_path / "manifest.jsonl",
        )


# 23. Sitemap discovery returns document URLs
def test_sitemap_discovers_urls():
    sitemap = b"""<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>https://example.com/guide1.pdf</loc></url>
        <url><loc>https://example.com/guide2.pdf</loc></url>
    </urlset>
    """

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=sitemap)

    result = asyncio.run(
        discover_sitemap_urls(
            "https://example.com/sitemap.xml",
            transport=make_transport(handler),
        )
    )

    assert result == [
        "https://example.com/guide1.pdf",
        "https://example.com/guide2.pdf",
    ]


# 24. Sitemap discovery applies the include filter
def test_sitemap_include_filter():
    sitemap = b"""<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>https://example.com/docs/guide.pdf</loc></url>
        <url><loc>https://example.com/images/photo.jpg</loc></url>
    </urlset>
    """

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=sitemap)

    result = asyncio.run(
        discover_sitemap_urls(
            "https://example.com/sitemap.xml",
            include="/docs/",
            transport=make_transport(handler),
        )
    )

    assert result == ["https://example.com/docs/guide.pdf"]


# 25. Sitemap discovery removes duplicate URLs
def test_sitemap_removes_duplicates():
    sitemap = b"""<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>https://example.com/guide.pdf</loc></url>
        <url><loc>https://example.com/guide.pdf</loc></url>
    </urlset>
    """

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=sitemap)

    result = asyncio.run(
        discover_sitemap_urls(
            "https://example.com/sitemap.xml",
            transport=make_transport(handler),
        )
    )

    assert result == ["https://example.com/guide.pdf"]


# 26. Sitemap discovery rejects robots.txt restrictions
def test_sitemap_robots_disallow():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /")
        return httpx.Response(200, content=b"<urlset/>")

    with pytest.raises(PermissionError):
        asyncio.run(
            discover_sitemap_urls(
                "https://example.com/sitemap.xml",
                transport=make_transport(handler),
            )
        )


# 27. Restart skips completed files and retries failed files
def test_restart_skips_completed_and_retries_failed(tmp_path):
    calls = {"first": 0, "second": 0}

    first_source = make_source("https://example.com/first.pdf")
    second_source = make_source("https://example.com/second.pdf")
    sources = [first_source, second_source]

    raw_dir = tmp_path / "raw"
    manifest = tmp_path / "manifest.jsonl"

    def first_run_handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)

        if request.url.path == "/first.pdf":
            calls["first"] += 1
            return httpx.Response(200, content=b"First document")

        calls["second"] += 1
        return httpx.Response(500)

    first_results = asyncio.run(
        fetch_sources(
            sources,
            raw_dir=raw_dir,
            manifest_path=manifest,
            transport=make_transport(first_run_handler),
            delay=0,
        )
    )

    assert first_results[0]["result"] == "downloaded"
    assert first_results[1]["result"] == "failed"

    def restart_handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)

        if request.url.path == "/first.pdf":
            calls["first"] += 1
            return httpx.Response(500)

        calls["second"] += 1
        return httpx.Response(200, content=b"Second document")

    restart_results = asyncio.run(
        fetch_sources(
            sources,
            raw_dir=raw_dir,
            manifest_path=manifest,
            transport=make_transport(restart_handler),
            delay=0,
        )
    )

    assert restart_results[0]["result"] == "skipped"
    assert restart_results[1]["result"] == "downloaded"

    assert calls["first"] == 1
    assert calls["second"] > 1

    first_filename = Fetcher._file_name(first_source["url"])
    second_filename = Fetcher._file_name(second_source["url"])

    assert (raw_dir / first_filename).exists()
    assert (raw_dir / second_filename).exists()
