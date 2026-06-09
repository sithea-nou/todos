"""Chat router: POST /api/chat."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.services import chat_service

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, Any]] = []


class ChatResponse(BaseModel):
    response: str


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Run a message through the todo AI agent."""
    reply = await chat_service.chat(request.message, request.history)
    return ChatResponse(response=reply)
