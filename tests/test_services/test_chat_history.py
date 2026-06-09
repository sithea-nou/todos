"""Tests for chat_history service (sessions + messages)."""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import chat_history


async def test_create_session_defaults_title(session: AsyncSession) -> None:
    s = await chat_history.create_session(session)
    assert s.id is not None
    assert s.title == "New chat"


async def test_create_session_custom_title(session: AsyncSession) -> None:
    s = await chat_history.create_session(session, title="My thread")
    assert s.title == "My thread"


async def test_list_sessions_orders_by_updated_at(session: AsyncSession) -> None:
    a = await chat_history.create_session(session, title="A")
    b = await chat_history.create_session(session, title="B")
    out = await chat_history.list_sessions(session)
    ids = [s.id for s in out]
    assert ids[0] == b.id
    assert ids[1] == a.id


async def test_add_message_auto_titles_from_user_message(session: AsyncSession) -> None:
    s = await chat_history.create_session(session)
    await chat_history.add_message(session, s.id, "user", "Buy milk and eggs")
    refreshed = await chat_history.get_session_or_none(session, s.id)
    assert refreshed is not None
    assert refreshed.title == "Buy milk and eggs"


async def test_add_message_does_not_overwrite_custom_title(session: AsyncSession) -> None:
    s = await chat_history.create_session(session, title="My plan")
    await chat_history.add_message(session, s.id, "user", "anything")
    refreshed = await chat_history.get_session_or_none(session, s.id)
    assert refreshed is not None
    assert refreshed.title == "My plan"


async def test_list_messages_preserves_order(session: AsyncSession) -> None:
    s = await chat_history.create_session(session)
    await chat_history.add_message(session, s.id, "user", "one")
    await chat_history.add_message(session, s.id, "assistant", "two")
    await chat_history.add_message(session, s.id, "user", "three")
    msgs = await chat_history.list_messages(session, s.id)
    assert [m.content for m in msgs] == ["one", "two", "three"]
    assert [m.role for m in msgs] == ["user", "assistant", "user"]


async def test_add_message_with_tool_calls_persists_json(session: AsyncSession) -> None:
    s = await chat_history.create_session(session)
    tool_calls = [
        {
            "id": "c1",
            "type": "function",
            "function": {"name": "create_todo", "arguments": '{"title":"x"}'},
        }
    ]
    await chat_history.add_message(
        session, s.id, "assistant", "", tool_calls=tool_calls
    )
    await chat_history.add_message(
        session, s.id, "tool", '{"id":"abc"}', tool_call_id="c1"
    )
    msgs = await chat_history.list_messages(session, s.id)
    assert msgs[0].tool_calls == tool_calls
    assert msgs[1].tool_call_id == "c1"


async def test_messages_to_history_round_trip(session: AsyncSession) -> None:
    s = await chat_history.create_session(session)
    tool_calls = [
        {
            "id": "c1",
            "type": "function",
            "function": {"name": "list_todos", "arguments": "{}"},
        }
    ]
    await chat_history.add_message(session, s.id, "user", "list my todos")
    await chat_history.add_message(
        session, s.id, "assistant", "", tool_calls=tool_calls
    )
    await chat_history.add_message(
        session, s.id, "tool", "[]", tool_call_id="c1"
    )
    await chat_history.add_message(session, s.id, "assistant", "All clear!")

    history = chat_history.messages_to_history(
        await chat_history.list_messages(session, s.id)
    )
    assert history[0] == {"role": "user", "content": "list my todos"}
    assert history[1] == {
        "role": "assistant",
        "content": "",
        "tool_calls": tool_calls,
    }
    assert history[2] == {"role": "tool", "tool_call_id": "c1", "content": "[]"}
    assert history[3] == {"role": "assistant", "content": "All clear!"}


async def test_delete_session_removes_messages(session: AsyncSession) -> None:
    s = await chat_history.create_session(session)
    await chat_history.add_message(session, s.id, "user", "x")
    assert await chat_history.delete_session(session, s.id) is True
    assert await chat_history.get_session_or_none(session, s.id) is None
    msgs = await chat_history.list_messages(session, s.id)
    assert msgs == []


async def test_delete_session_returns_false_when_missing(session: AsyncSession) -> None:
    assert await chat_history.delete_session(session, uuid4()) is False


async def test_add_message_raises_for_missing_session(session: AsyncSession) -> None:
    import pytest

    with pytest.raises(ValueError, match="not found"):
        await chat_history.add_message(session, uuid4(), "user", "x")
