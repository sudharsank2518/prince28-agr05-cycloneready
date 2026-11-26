"""Tests for chat, streaming, usage, and LLM status endpoints."""

from types import SimpleNamespace
from unittest.mock import AsyncMock


def make_mock_gateway(classification="docs"):
    """Create a gateway mock without making real provider calls."""

    gateway = SimpleNamespace()
    gateway.system_prompt = "You are CycloneReady."

    classifier_result = SimpleNamespace(
        content=classification,
        text=classification,
        provider="gemini",
        model="gemini-3.5-flash-lite",
        request_id="classifier-request",
        input_tokens=5,
        output_tokens=1,
        latency_ms=50,
        fallback_used=False,
        cost_inr=0.001,
    )

    chat_result = SimpleNamespace(
        content="Stay safe during a cyclone.",
        provider="gemini",
        model="gemini-3.5-flash-lite",
        request_id="test-request-123",
        input_tokens=10,
        output_tokens=8,
        latency_ms=150,
        fallback_used=False,
        cost_inr=0.001,
    )

    gateway.generate = AsyncMock(side_effect=[classifier_result, chat_result])

    async def stream(messages, **kwargs):
        yield {
            "content": "Stay safe",
            "provider": "gemini",
            "model": "gemini-3.5-flash-lite",
        }
        yield {
            "event": "done",
            "content": "",
            "provider": "gemini",
            "model": "gemini-3.5-flash-lite",
        }

    gateway.stream = stream
    return gateway


def test_chat_returns_llm_response(client):
    gateway = make_mock_gateway()
    client.app.state.llm_gateway = gateway

    response = client.post(
        "/v1/chat",
        json={"messages": [{"role": "user", "content": "How do I prepare for a cyclone?"}]},
    )

    assert response.status_code == 200

    body = response.json()
    assert body["answer"] == "Stay safe during a cyclone."
    assert body["provider"] == "gemini"
    assert body["model"] == "gemini-3.5-flash-lite"
    assert body["fallback_used"] is False
    assert body["cost_inr"] == 0.001

    sent_messages = gateway.generate.call_args.args[0]

    assert sent_messages[0]["role"] == "system"
    assert sent_messages[0]["content"] == "You are CycloneReady."
    assert sent_messages[1]["content"] == "How do I prepare for a cyclone?"


def test_chat_streams_sse_events(client):
    gateway = make_mock_gateway()
    client.app.state.llm_gateway = gateway

    response = client.post(
        "/v1/chat",
        json={
            "messages": [{"role": "user", "content": "Explain cyclone safety."}],
            "stream": True,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "Stay safe" in response.text
    assert '"event": "done"' in response.text


def test_chat_keeps_only_six_previous_messages_and_current(client):
    gateway = make_mock_gateway()
    client.app.state.llm_gateway = gateway

    messages = [{"role": "user", "content": f"Message {number}"} for number in range(1, 10)]

    response = client.post(
        "/v1/chat",
        json={"messages": messages},
    )

    assert response.status_code == 200

    sent_messages = gateway.generate.call_args.args[0]

    # First message is the system prompt.
    conversation = sent_messages[1:]

    assert len(conversation) == 7
    assert conversation[0]["content"] == "Message 3"
    assert conversation[-1]["content"] == "Message 9"


def test_get_daily_usage(client):
    response = client.get("/v1/usage")

    assert response.status_code == 200
    assert isinstance(response.json(), dict)


def test_llm_status_reports_provider_circuits(client):
    response = client.get("/v1/llm/status")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "ok"
    assert body["primary"]["provider"] == "gemini"
    assert body["fallback"]["provider"] == "groq"
    assert body["primary"]["circuit"] in {"closed", "open", "half_open"}
    assert body["fallback"]["circuit"] in {"closed", "open", "half_open"}


def test_chat_personal_question_uses_fixed_answer_without_second_llm_call(client):
    gateway = make_mock_gateway(classification="personal")
    client.app.state.llm_gateway = gateway

    response = client.post(
        "/v1/chat",
        json={"messages": [{"role": "user", "content": "Is there a cyclone warning near me?"}]},
    )

    assert response.status_code == 200
    assert "can't verify live conditions" in response.json()["answer"]
    assert gateway.generate.await_count == 1


def test_chat_off_topic_question_uses_fixed_answer_without_second_llm_call(client):
    gateway = make_mock_gateway(classification="off_topic")
    client.app.state.llm_gateway = gateway

    response = client.post(
        "/v1/chat",
        json={"messages": [{"role": "user", "content": "Who won the cricket match?"}]},
    )

    assert response.status_code == 200
    assert "I'm CycloneReady" in response.json()["answer"]
    assert gateway.generate.await_count == 1
