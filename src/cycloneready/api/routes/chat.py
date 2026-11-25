"""Chat and LLM usage endpoints."""

import json
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from cycloneready.api.deps import DbSessionDep, LLMGatewayDep
from cycloneready.db.llm_calls import LlmCallRepository

router = APIRouter(tags=["chat"])


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


@router.post("/chat")
async def chat(
    body: ChatRequest,
    gateway: LLMGatewayDep,
):
    """Generate a CycloneReady response, optionally using SSE streaming."""

    # Keep the six previous messages and the current message.
    conversation = body.messages[-7:]

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

    return {
        "answer": result.content,
        "provider": result.provider,
        "model": result.model,
        "request_id": result.request_id,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "latency_ms": result.latency_ms,
        "fallback_used": result.fallback_used,
        "cost_inr": result.cost_inr,
    }


@router.get("/usage")
async def get_usage(
    session: DbSessionDep,
    usage_date: date | None = None,
) -> dict:
    """Return recorded LLM usage for a date (today by default)."""

    # Use Indian Standard Time instead of the container's UTC date.
    selected_date = usage_date or datetime.now(ZoneInfo("Asia/Kolkata")).date()

    repository = LlmCallRepository(session)

    return await repository.get_daily_usage(selected_date)
