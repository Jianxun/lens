from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.services.agent import AgentService, stream_answer

STREAM_MEDIA_TYPE = "text/event-stream"

router = APIRouter(prefix="/chat", tags=["chat"])


def _get_state(request: Request) -> tuple[str, httpx.Client]:
    dsn = getattr(request.app.state, "dsn", None)
    client = getattr(request.app.state, "embedding_client", None)
    if not dsn:
        raise HTTPException(status_code=500, detail="Database DSN not configured")
    if client is None:
        raise HTTPException(status_code=500, detail="Chat client not configured")
    return dsn, client


def _last_user_content(messages: List[Dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                return content
    raise HTTPException(status_code=400, detail="At least one non-empty user message is required")


class ChatMessage(BaseModel):
    role: str = Field(..., description="Message role: user/assistant/system")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., description="OpenAI-style message array (must include a user message)")
    model: Optional[str] = Field(None, description="Optional model override for downstream chat completion")
    max_tokens: Optional[int] = Field(None, description="Optional max completion tokens")
    max_completion_tokens: Optional[int] = Field(None, description="Alias for max_tokens")


@router.post("", response_class=StreamingResponse)
async def chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    messages = [msg.model_dump() for msg in payload.messages]
    if not messages:
        raise HTTPException(status_code=400, detail="messages are required")

    user_query = _last_user_content(messages)
    dsn, client = _get_state(request)

    service = AgentService(dsn, embedding_client=client)
    final_answer, metadata = service.run(user_query)

    stream = stream_answer(final_answer, metadata)
    return StreamingResponse(stream, media_type=STREAM_MEDIA_TYPE)

