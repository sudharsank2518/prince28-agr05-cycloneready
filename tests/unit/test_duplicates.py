import json

from scripts import find_duplicates


def write_manifest(path, records):
    """Write test records to a temporary manifest."""
    content = "\n".join(json.dumps(record) for record in records)
    path.write_text(content + "\n", encoding="utf-8")


def test_find_duplicates_detects_matching_hashes(tmp_path, monkeypatch, capsys):
    manifest = tmp_path / "manifest.jsonl"

    records = [
        {
            "url": "https://example.com/one.pdf",
            "status": "downloaded",
            "sha256": "abc123",
            "file_path": "data/raw/one.pdf",
        },
        {
            "url": "https://example.com/two.pdf",
            "status": "downloaded",
            "sha256": "abc123",
            "file_path": "data/raw/two.pdf",
        },
    ]

    write_manifest(manifest, records)
    monkeypatch.setattr(find_duplicates, "MANIFEST", manifest)

    find_duplicates.find_duplicates()

    output = capsys.readouterr().out

    assert "Duplicate groups found: 1" in output
    assert "data/raw/one.pdf" in output
    assert "data/raw/two.pdf" in output


def test_find_duplicates_ignores_failed_downloads(tmp_path, monkeypatch, capsys):
    manifest = tmp_path / "manifest.jsonl"

    records = [
        {
            "url": "https://example.com/one.pdf",
            "status": "downloaded",
            "sha256": "abc123",
            "file_path": "data/raw/one.pdf",
        },
        {
            "url": "https://example.com/two.pdf",
            "status": "failed",
            "sha256": "abc123",
            "file_path": "data/raw/two.pdf",
        },
    ]

    write_manifest(manifest, records)
    monkeypatch.setattr(find_duplicates, "MANIFEST", manifest)

    find_duplicates.find_duplicates()

    output = capsys.readouterr().out

    assert "No duplicate files found." in output


def test_find_duplicates_handles_missing_manifest(tmp_path, monkeypatch, capsys):
    manifest = tmp_path / "missing.jsonl"
    monkeypatch.setattr(find_duplicates, "MANIFEST", manifest)

    find_duplicates.find_duplicates()

    output = capsys.readouterr().out

    assert "Manifest not found." in output
