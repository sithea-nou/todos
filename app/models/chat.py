"""SQLModel ORM models for chat sessions and messages."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class ChatSession(SQLModel, table=True):
    """A persisted chat conversation thread."""

    __tablename__ = "chat_sessions"

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    title: str = Field(default="New chat", min_length=1, max_length=200)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ChatMessage(SQLModel, table=True):
    """A single message inside a chat session.

    ``role`` is one of ``user``, ``assistant``, ``tool``, ``system``.
    ``content`` is the message text (may be empty for assistant tool-call turns).
    ``tool_calls`` / ``tool_call_id`` capture the OpenAI-style tool-use
    protocol so the LLM sees a faithful history on subsequent turns.
    """

    __tablename__ = "chat_messages"

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    session_id: UUID = Field(foreign_key="chat_sessions.id", index=True)
    role: str = Field(min_length=1, max_length=20)
    content: str = Field(default="")
    tool_calls: str | None = Field(default=None)  # JSON list of tool calls
    tool_call_id: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)


class ChatSessionRead(SQLModel):
    """Schema for reading a chat session."""

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ChatSessionCreate(SQLModel):
    """Schema for creating a chat session."""

    title: str | None = Field(default=None, max_length=200)


class ChatMessageRead(SQLModel):
    """Schema for reading a chat message."""

    id: UUID
    session_id: UUID
    role: str
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    created_at: datetime
