"""Tests for structured document metadata extraction."""

import asyncio
import json

import pytest

from cycloneready.llm.doc_meta import DocMeta
from cycloneready.llm.extract import (
    ExtractionError,
    build_messages,
    extract_metadata,
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
            "Cyclone preparedness guide.",
        )
    )

    assert isinstance(metadata, DocMeta)
    assert metadata.doc_kind == "guideline"
    assert metadata.year == 2024
    assert metadata.hazard == ["cyclone"]
    assert result.text == json.dumps(VALID_METADATA)
    assert primary.calls == 1


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
