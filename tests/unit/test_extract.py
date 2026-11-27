"""Tests for structured document metadata extraction."""

import asyncio
import json

import pytest

from cycloneready.llm.doc_meta import DocMeta
from cycloneready.llm.extract import (
    ExtractionError,
    build_messages,
    chunk_pages,
    extract_metadata,
    merge_metadata,
    metadata_response_format,
)
from cycloneready.llm.gateway import FakeLLMProvider, LLMGateway

VALID_METADATA = {
    "doc_kind": "guideline",
    "year": 2024,
    "language": "English",
    "summary": "Guidance for cyclone preparedness.",
    "topics": ["emergency kit", "evacuation"],
    "hazard": ["cyclone"],
    "phase": ["preparedness"],
    "action": ["Prepare emergency supplies"],
    "responsible": ["Families"],
    "warning_stage": [],
}


def make_gateway(response: str):
    """Create a gateway that uses fake providers without API calls."""
    primary = FakeLLMProvider(
        name="primary",
        response=response,
    )
    fallback = FakeLLMProvider(name="fallback")

    return LLMGateway(primary, fallback), primary


def test_build_messages_wraps_document_text():
    messages = build_messages(
        "Extract document metadata.",
        "  Cyclone preparedness guide.  ",
    )

    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "Extract document metadata."
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == ("<document>\nCyclone preparedness guide.\n</document>")


def test_extract_metadata_returns_validated_metadata():
    gateway, primary = make_gateway(json.dumps(VALID_METADATA))

    metadata, result = asyncio.run(
        extract_metadata(
            gateway,
            "Extract document metadata.",
            "v1",
            "Cyclone preparedness guide published in 2024.",
        )
    )

    assert isinstance(metadata, DocMeta)
    assert metadata.doc_kind == "guideline"
    assert metadata.year == 2024
    assert metadata.hazard == ["cyclone"]
    assert result.text == json.dumps(VALID_METADATA)
    assert primary.calls == 1
    assert primary.response_formats == [metadata_response_format()]


def test_metadata_response_format_is_strict_and_requires_all_fields():
    response_format = metadata_response_format()

    assert response_format["type"] == "json_schema"

    json_schema = response_format["json_schema"]
    assert json_schema["strict"] is True

    schema = json_schema["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])

    year_schema = schema["properties"]["year"]
    assert year_schema["anyOf"] == [
        {"type": "integer"},
        {"type": "null"},
    ]


def test_extract_metadata_rejects_invalid_json():
    gateway, primary = make_gateway("This is not JSON.")

    with pytest.raises(ExtractionError, match="invalid JSON"):
        asyncio.run(
            extract_metadata(
                gateway,
                "Extract document metadata.",
                "v1",
                "Cyclone preparedness guide.",
            )
        )

    assert primary.calls == 1


def test_extract_metadata_rejects_invalid_fields():
    invalid_metadata = {
        **VALID_METADATA,
        "doc_kind": "unknown_kind",
    }
    gateway, primary = make_gateway(json.dumps(invalid_metadata))

    with pytest.raises(ExtractionError, match="DocMeta validation"):
        asyncio.run(
            extract_metadata(
                gateway,
                "Extract document metadata.",
                "v1",
                "Cyclone preparedness guide.",
            )
        )

    assert primary.calls == 1


def test_extract_metadata_rejects_empty_document():
    gateway, primary = make_gateway(json.dumps(VALID_METADATA))

    with pytest.raises(ExtractionError, match="empty document"):
        asyncio.run(
            extract_metadata(
                gateway,
                "Extract document metadata.",
                "v1",
                "   ",
            )
        )

    assert primary.calls == 0


def test_extract_metadata_accepts_unknown_publication_year():
    metadata_without_year = {
        **VALID_METADATA,
        "year": None,
    }
    gateway, primary = make_gateway(json.dumps(metadata_without_year))

    metadata, _ = asyncio.run(
        extract_metadata(
            gateway,
            "Return null when publication year is uncertain.",
            "v1",
            (
                "Guidelines on disaster management. "
                "Refers to the Disaster Management Amendment Act, 2025. "
                "No publication date is provided."
            ),
        )
    )

    assert metadata.year is None
    assert primary.calls == 1


def test_chunk_pages_groups_text_within_limit():
    page_texts = [
        "Page one text.",
        "Page two text.",
        "Page three text.",
    ]

    chunks = chunk_pages(page_texts, max_chars=35)

    assert len(chunks) >= 2
    assert all(len(chunk) <= 35 for chunk in chunks)

    original_words = " ".join(page_texts).split()
    extracted_words = " ".join(chunks).split()

    assert extracted_words == original_words


def test_chunk_pages_splits_large_pages_without_losing_text():
    page = "word " * 100

    chunks = chunk_pages([page], max_chars=30)

    assert len(chunks) > 1
    assert all(len(chunk) <= 30 for chunk in chunks)
    assert " ".join(chunks).replace("\n", " ").split() == page.split()


def test_chunk_pages_rejects_invalid_limit():
    with pytest.raises(ValueError, match="at least 1"):
        chunk_pages(["Some text"], max_chars=0)


def test_chunk_pages_skips_empty_pages():
    chunks = chunk_pages(["", "  ", "Useful page text"])

    assert chunks == ["Useful page text"]


def test_merge_metadata_combines_unique_values():
    first = DocMeta.model_validate(VALID_METADATA)
    second = DocMeta.model_validate(
        {
            **VALID_METADATA,
            "topics": ["evacuation", "flood safety"],
            "hazard": ["flood"],
            "phase": ["response"],
            "action": ["Move to a safe location"],
            "responsible": ["Local authorities"],
            "warning_stage": ["Red"],
        }
    )

    merged = merge_metadata([first, second])

    assert merged.topics == ["emergency kit", "evacuation", "flood safety"]
    assert merged.hazard == ["cyclone", "flood"]
    assert merged.phase == ["preparedness", "response"]
    assert merged.action == [
        "Prepare emergency supplies",
        "Move to a safe location",
    ]
    assert merged.responsible == ["Families", "Local authorities"]
    assert merged.warning_stage == ["Red"]


def test_merge_metadata_clears_conflicting_years():
    first = DocMeta.model_validate(VALID_METADATA)
    second = DocMeta.model_validate({**VALID_METADATA, "year": 2025})

    merged = merge_metadata([first, second])

    assert merged.year is None


def test_merge_metadata_clears_year_when_another_chunk_has_no_year():
    first = DocMeta.model_validate(VALID_METADATA)
    second = DocMeta.model_validate({**VALID_METADATA, "year": None})

    merged = merge_metadata([first, second])

    assert merged.year is None


def test_merge_metadata_rejects_empty_results():
    with pytest.raises(ExtractionError, match="No chunk metadata"):
        merge_metadata([])
