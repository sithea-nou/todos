"""Chat session REST API: list/create/delete sessions and load history."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.chat import (
    ChatMessageRead,
    ChatSessionCreate,
    ChatSessionRead,
)
from app.services import chat_history

router = APIRouter()


@router.get("/sessions", response_model=list[ChatSessionRead])
async def list_sessions(
    session: AsyncSession = Depends(get_session),
) -> list[ChatSessionRead]:
    """List all chat sessions, most recently updated first."""
    return await chat_history.list_sessions(session)


@router.post("/sessions", response_model=ChatSessionRead, status_code=201)
async def create_session(
    data: ChatSessionCreate | None = None,
    session: AsyncSession = Depends(get_session),
) -> ChatSessionRead:
    """Create a new chat session. Title is optional."""
    title = data.title if data else None
    return await chat_history.create_session(session, title=title)


@router.get("/sessions/{session_id}", response_model=ChatSessionRead)
async def get_session_endpoint(
    session_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ChatSessionRead:
    """Fetch a single chat session by id."""
    obj = await chat_history.get_session_or_none(session, session_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return obj


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session_endpoint(
    session_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a chat session and all of its messages."""
    deleted = await chat_history.delete_session(session, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Chat session not found")


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageRead])
async def list_session_messages(
    session_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[ChatMessageRead]:
    """Return all messages for a chat session, oldest first."""
    obj = await chat_history.get_session_or_none(session, session_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return await chat_history.list_messages(session, session_id)


def _extras() -> dict[str, Any]:
    """Exposed for backwards-compat re-exports in tests if needed."""
    return {}
