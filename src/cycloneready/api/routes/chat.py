"""Chat and LLM usage endpoints."""

import json
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from cycloneready.api.deps import DbSessionDep, LLMGatewayDep, SettingsDep
from cycloneready.db.llm_calls import LlmCallRepository
from cycloneready.llm.classify import classify
from cycloneready.llm.gateway import GatewayResponse

router = APIRouter(tags=["chat"])

CLASSIFIER_VERSION = "4"

FIXED_ANSWERS = {
    "personal": (
        "I can't verify live conditions, current alerts, or personal emergency "
        "situations. Please check the latest official IMD and Tamil Nadu "
        "disaster-management alerts, and contact local emergency services "
        "if you may be in danger."
    ),
    "off_topic": (
        "I'm CycloneReady, and I can help with cyclone preparedness, flooding, "
        "and disaster-management guidance. Please ask a question related to "
        "those topics."
    ),
}


class ChatMessage(BaseModel):
    """One message in a conversation."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""

    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1000, ge=1, le=8000)


def response_body(answer: str, result: GatewayResponse) -> dict:
    """Build the standard chat response."""

    return {
        "answer": answer,
        "provider": result.provider,
        "model": result.model,
        "request_id": result.request_id,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "latency_ms": result.latency_ms,
        "fallback_used": result.fallback_used,
        "cost_inr": result.cost_inr,
    }


@router.post("/chat")
async def chat(
    body: ChatRequest,
    gateway: LLMGatewayDep,
    settings: SettingsDep,
):
    """Classify the question, then answer document questions."""

    conversation = body.messages[-7:]
    question = next(
        (message.content for message in reversed(conversation) if message.role == "user"),
        None,
    )
    if question is None:
        raise HTTPException(status_code=400, detail="A user message is required.")

    prompt_path = settings.prompts_dir / f"classify_v{CLASSIFIER_VERSION}.md"
    if not prompt_path.is_file():
        raise HTTPException(status_code=500, detail="The question-classifier prompt is missing.")

    classifier_prompt = prompt_path.read_text(encoding="utf-8")
    label, classification_result = await classify(
        gateway,
        classifier_prompt,
        CLASSIFIER_VERSION,
        question,
    )

    if label == "invalid":
        answer = (
            "I couldn't confidently classify your question. Please rephrase it "
            "as a question about cyclone preparedness, flooding, or disaster management."
        )
        if body.stream:

            async def invalid_stream():
                yield f"data: {json.dumps({'content': answer})}\n\n"
                yield f"data: {json.dumps({'event': 'done', 'content': ''})}\n\n"

            return StreamingResponse(invalid_stream(), media_type="text/event-stream")

        return response_body(answer, classification_result)

    if label in FIXED_ANSWERS:
        answer = FIXED_ANSWERS[label]

        if body.stream:

            async def fixed_stream():
                provider_info = {
                    "provider": classification_result.provider,
                    "model": classification_result.model,
                }
                answer_event = {"content": answer, **provider_info}
                done_event = {"event": "done", "content": "", **provider_info}

                yield f"data: {json.dumps(answer_event)}\\n\\n"
                yield f"data: {json.dumps(done_event)}\\n\\n"

            return StreamingResponse(fixed_stream(), media_type="text/event-stream")

        return response_body(answer, classification_result)

    messages = [
        {
            "role": "system",
            "content": gateway.system_prompt,
        },
        *[{"role": message.role, "content": message.content} for message in conversation],
    ]

    if body.stream:

        async def event_stream():
            async for event in gateway.stream(
                messages,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
            ):
                yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    result = await gateway.generate(
        messages,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
    )

    return response_body(result.content, result)


@router.get("/usage")
async def get_usage(
    session: DbSessionDep,
    usage_date: date | None = None,
) -> dict:
    """Return recorded LLM usage for a date (today by default)."""

    selected_date = usage_date or datetime.now(ZoneInfo("Asia/Kolkata")).date()
    repository = LlmCallRepository(session)

    return await repository.get_daily_usage(selected_date)
