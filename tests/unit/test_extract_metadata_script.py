from scripts.extract_metadata import create_fingerprints, get_resume_metadata

VALID_METADATA = {
    "doc_kind": "guideline",
    "year": 2025,
    "language": "English",
    "summary": "Cyclone preparedness guidance.",
    "topics": ["evacuation", "safety"],
    "hazard": ["cyclone"],
    "phase": ["preparedness"],
    "action": ["Prepare emergency kits"],
    "responsible": ["Residents"],
    "warning_stage": [],
}


def make_progress(fingerprints, metadata=None):
    """Build a sample interrupted extraction progress record."""
    metadata = [VALID_METADATA] if metadata is None else metadata

    return {
        "status": "in_progress",
        "prompt_version": "v1",
        **fingerprints,
        "completed_chunks": len(metadata),
        "chunk_count": 2,
        "chunk_metadata": metadata,
    }


def test_create_fingerprints_returns_stable_hashes():
    first = create_fingerprints("prompt text", ["chunk one", "chunk two"])
    second = create_fingerprints("prompt text", ["chunk one", "chunk two"])

    assert first == second
    assert len(first["prompt_hash"]) == 64
    assert len(first["content_hash"]) == 64


def test_resume_when_prompt_and_content_match():
    fingerprints = create_fingerprints("prompt text", ["chunk one", "chunk two"])
    progress = make_progress(fingerprints)

    metadata, can_resume = get_resume_metadata(progress, "v1", fingerprints, 2, False)

    assert can_resume is True
    assert len(metadata) == 1


def test_do_not_resume_when_prompt_changes():
    fingerprints = create_fingerprints("prompt text", ["chunk one", "chunk two"])
    changed = {
        **fingerprints,
        "prompt_hash": "different",
    }
    progress = make_progress(fingerprints)

    metadata, can_resume = get_resume_metadata(progress, "v1", changed, 2, False)

    assert can_resume is False
    assert metadata == []


def test_do_not_resume_when_document_content_changes():
    fingerprints = create_fingerprints("prompt text", ["chunk one", "chunk two"])
    changed = {
        **fingerprints,
        "content_hash": "different",
    }
    progress = make_progress(fingerprints)

    metadata, can_resume = get_resume_metadata(progress, "v1", changed, 2, False)

    assert can_resume is False
    assert metadata == []


def test_do_not_resume_when_prompt_version_changes():
    fingerprints = create_fingerprints("prompt text", ["chunk one", "chunk two"])
    progress = make_progress(fingerprints)

    metadata, can_resume = get_resume_metadata(progress, "v2", fingerprints, 2, False)

    assert can_resume is False
    assert metadata == []


def test_do_not_resume_when_chunk_count_changes():
    fingerprints = create_fingerprints("prompt text", ["chunk one", "chunk two"])
    progress = make_progress(fingerprints)

    metadata, can_resume = get_resume_metadata(progress, "v1", fingerprints, 3, False)

    assert can_resume is False
    assert metadata == []


def test_do_not_resume_when_completed_count_is_inconsistent():
    fingerprints = create_fingerprints("prompt text", ["chunk one", "chunk two"])
    progress = make_progress(fingerprints)
    progress["completed_chunks"] = 2

    metadata, can_resume = get_resume_metadata(progress, "v1", fingerprints, 2, False)

    assert can_resume is False
    assert metadata == []


def test_do_not_resume_when_saved_metadata_is_invalid():
    fingerprints = create_fingerprints("prompt text", ["chunk one", "chunk two"])
    progress = make_progress(fingerprints, metadata=[{"invalid": True}])

    metadata, can_resume = get_resume_metadata(progress, "v1", fingerprints, 2, False)

    assert can_resume is False
    assert metadata == []


def test_reprocess_disables_resume():
    fingerprints = create_fingerprints("prompt text", ["chunk one", "chunk two"])
    progress = make_progress(fingerprints)

    metadata, can_resume = get_resume_metadata(progress, "v1", fingerprints, 2, True)

    assert can_resume is False
    assert metadata == []
