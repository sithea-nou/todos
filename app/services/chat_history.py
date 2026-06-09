"""Chat session + message persistence service."""

import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.chat import (
    ChatMessage,
    ChatMessageRead,
    ChatSession,
    ChatSessionRead,
)


def _to_read(msg: ChatMessage) -> ChatMessageRead:
    """ORM → ChatMessageRead, decoding the JSON tool_calls column."""
    tool_calls: list[dict[str, Any]] | None = None
    if msg.tool_calls:
        try:
            decoded = json.loads(msg.tool_calls)
            if isinstance(decoded, list):
                tool_calls = decoded
        except json.JSONDecodeError:
            tool_calls = None
    return ChatMessageRead(
        id=msg.id,
        session_id=msg.session_id,
        role=msg.role,
        content=msg.content,
        tool_calls=tool_calls,
        tool_call_id=msg.tool_call_id,
        created_at=msg.created_at,
    )


async def list_sessions(session: AsyncSession) -> list[ChatSessionRead]:
    """Return all chat sessions, most recently updated first."""
    stmt = select(ChatSession).order_by(ChatSession.updated_at.desc())
    result = await session.execute(stmt)
    sessions = result.scalars().all()
    return [ChatSessionRead(**s.model_dump()) for s in sessions]


async def create_session(
    session: AsyncSession, title: str | None = None
) -> ChatSessionRead:
    """Create a new chat session."""
    chat_session = ChatSession(title=title or "New chat")
    session.add(chat_session)
    await session.commit()
    await session.refresh(chat_session)
    return ChatSessionRead(**chat_session.model_dump())


async def get_session_or_none(
    session: AsyncSession, session_id: UUID
) -> ChatSessionRead | None:
    """Return a session by id, or None if it doesn't exist."""
    obj = await session.get(ChatSession, session_id)
    return ChatSessionRead(**obj.model_dump()) if obj else None


async def delete_session(session: AsyncSession, session_id: UUID) -> bool:
    """Delete a session and all its messages. Returns True if anything was deleted."""
    obj = await session.get(ChatSession, session_id)
    if obj is None:
        return False
    msgs_stmt = select(ChatMessage).where(ChatMessage.session_id == session_id)
    msgs = (await session.execute(msgs_stmt)).scalars().all()
    for m in msgs:
        await session.delete(m)
    await session.delete(obj)
    await session.commit()
    return True


async def list_messages(
    session: AsyncSession, session_id: UUID
) -> list[ChatMessageRead]:
    """Return all messages for a session in chronological order."""
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    result = await session.execute(stmt)
    return [_to_read(m) for m in result.scalars().all()]


async def add_message(
    session: AsyncSession,
    session_id: UUID,
    role: str,
    content: str,
    *,
    tool_calls: list[dict[str, Any]] | None = None,
    tool_call_id: str | None = None,
) -> ChatMessageRead:
    """Persist a single message. Bumps the session's updated_at."""
    chat_session = await session.get(ChatSession, session_id)
    if chat_session is None:
        raise ValueError(f"Chat session {session_id} not found")
    chat_session.updated_at = chat_session.updated_at  # touched via refresh below

    msg = ChatMessage(
        id=uuid4(),
        session_id=session_id,
        role=role,
        content=content,
        tool_calls=json.dumps(tool_calls) if tool_calls else None,
        tool_call_id=tool_call_id,
    )
    session.add(msg)
    # Update session timestamp manually (SQLModel default isn't auto-refreshed)
    from datetime import datetime

    chat_session.updated_at = datetime.now()
    if role == "user" and chat_session.title == "New chat":
        # Auto-title from the first user message (truncated to 60 chars)
        chat_session.title = content[:60] or "New chat"
    await session.commit()
    await session.refresh(msg)
    await session.refresh(chat_session)
    return _to_read(msg)


def messages_to_history(messages: list[ChatMessageRead]) -> list[dict[str, Any]]:
    """Convert persisted messages to the OpenAI chat-completions message format.

    Tool-call turns are reconstructed with their original ``tool_calls`` block;
    tool results are returned with their ``tool_call_id``.
    """
    history: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "assistant" and m.tool_calls:
            history.append(
                {
                    "role": "assistant",
                    "content": m.content,
                    "tool_calls": m.tool_calls,
                }
            )
        elif m.role == "tool":
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": m.tool_call_id or "",
                    "content": m.content,
                }
            )
        else:
            history.append({"role": m.role, "content": m.content})
    return history
