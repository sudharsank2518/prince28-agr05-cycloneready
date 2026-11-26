"""Tests for CycloneReady question classification."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from cycloneready.llm.classify import (
    accuracy,
    build_messages,
    classify,
    find_leaks,
    parse_label,
)


def test_build_messages_separates_prompt_and_question():
    messages = build_messages("System instructions", "Will it rain tomorrow?")

    assert messages[0] == {
        "role": "system",
        "content": "System instructions",
    }
    assert messages[1]["role"] == "user"
    assert "<question>" in messages[1]["content"]
    assert "Will it rain tomorrow?" in messages[1]["content"]
    assert "</question>" in messages[1]["content"]


def test_build_messages_strips_question_whitespace():
    messages = build_messages("Instructions", "  Hello there!  ")

    assert messages[1]["content"] == ("<question>\nHello there!\n</question>")


def test_parse_label_accepts_valid_labels():
    assert parse_label("docs") == "docs"
    assert parse_label("PERSONAL") == "personal"
    assert parse_label("Off-topic.") == "off_topic"
    assert parse_label("off_topic") == "off_topic"


def test_parse_label_rejects_invalid_or_ambiguous_replies():
    assert parse_label("unknown") == "invalid"
    assert parse_label("docs and personal") == "invalid"
    assert parse_label("") == "invalid"


def test_accuracy_calculates_correct_predictions():
    rows = [
        {"label": "docs", "got": "docs"},
        {"label": "personal", "got": "personal"},
        {"label": "off_topic", "got": "docs"},
        {"label": "docs", "got": "docs"},
    ]

    assert accuracy(rows) == 0.75
    assert accuracy([]) == 0.0


def test_find_leaks_detects_questions_in_prompt():
    prompt = """
    Example question:
    What are cyclone warning stages?
    """

    questions = [
        "What are cyclone warning stages?",
        "Will the cyclone hit Chennai tomorrow?",
    ]

    assert find_leaks(prompt, questions) == ["What are cyclone warning stages?"]


def test_classify_calls_gateway_and_returns_label():
    result = SimpleNamespace(text="DOCS")
    gateway = SimpleNamespace(generate=AsyncMock(return_value=result))

    label, returned_result = asyncio.run(
        classify(
            gateway,
            "Classify the question.",
            "v2",
            "What are cyclone warning stages?",
        )
    )

    assert label == "docs"
    assert returned_result is result

    gateway.generate.assert_awaited_once()
    call = gateway.generate.call_args

    assert call.kwargs["purpose"] == "classify"
    assert call.kwargs["prompt_version"] == "v2"
    assert call.kwargs["temperature"] == 0
    assert call.args[0][0]["role"] == "system"
    assert call.args[0][1]["role"] == "user"
