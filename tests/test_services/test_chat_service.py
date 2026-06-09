"""Tests for the chat_service layer."""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.chat_service as cs
from app.models.todo import TodoCreate
from app.services import todo_service


@pytest_asyncio.fixture
async def patched_session(session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """Patch chat_service to use the test DB session."""

    @asynccontextmanager
    async def _factory() -> AsyncGenerator[AsyncSession, None]:
        yield session

    original = cs.async_session_factory
    cs.async_session_factory = _factory  # type: ignore[assignment]
    yield session
    cs.async_session_factory = original  # type: ignore[assignment]


# --- _run_tool tests ---


async def test_run_tool_list_todos_empty(patched_session: AsyncSession) -> None:
    result = await cs._run_tool("list_todos", {})
    assert json.loads(result) == []


async def test_run_tool_list_todos(patched_session: AsyncSession) -> None:
    await todo_service.create_todo(patched_session, TodoCreate(title="A"))
    await todo_service.create_todo(patched_session, TodoCreate(title="B"))
    result = await cs._run_tool("list_todos", {})
    assert len(json.loads(result)) == 2


async def test_run_tool_list_todos_filter_completed(patched_session: AsyncSession) -> None:
    await todo_service.create_todo(patched_session, TodoCreate(title="Active"))
    await todo_service.create_todo(patched_session, TodoCreate(title="Done", is_completed=True))
    result = await cs._run_tool("list_todos", {"completed": True})
    todos = json.loads(result)
    assert len(todos) == 1
    assert todos[0]["title"] == "Done"


async def test_run_tool_create_todo(patched_session: AsyncSession) -> None:
    result = await cs._run_tool("create_todo", {"title": "New task", "description": "Details"})
    data = json.loads(result)
    assert data["title"] == "New task"
    assert data["description"] == "Details"
    assert data["is_completed"] is False


async def test_run_tool_get_todo(patched_session: AsyncSession) -> None:
    created = await todo_service.create_todo(patched_session, TodoCreate(title="Find me"))
    result = await cs._run_tool("get_todo", {"todo_id": str(created.id)})
    assert json.loads(result)["title"] == "Find me"


async def test_run_tool_get_todo_not_found(patched_session: AsyncSession) -> None:
    result = await cs._run_tool("get_todo", {"todo_id": str(uuid4())})
    assert "not found" in result


async def test_run_tool_get_todo_invalid_uuid(patched_session: AsyncSession) -> None:
    result = await cs._run_tool("get_todo", {"todo_id": "not-a-uuid"})
    assert "Invalid todo_id" in result


async def test_run_tool_update_todo(patched_session: AsyncSession) -> None:
    created = await todo_service.create_todo(patched_session, TodoCreate(title="Old"))
    result = await cs._run_tool(
        "update_todo",
        {"todo_id": str(created.id), "title": "New", "is_completed": True},
    )
    data = json.loads(result)
    assert data["title"] == "New"
    assert data["is_completed"] is True


async def test_run_tool_update_todo_not_found(patched_session: AsyncSession) -> None:
    result = await cs._run_tool("update_todo", {"todo_id": str(uuid4()), "title": "X"})
    assert "not found" in result


async def test_run_tool_delete_todo(patched_session: AsyncSession) -> None:
    created = await todo_service.create_todo(patched_session, TodoCreate(title="Bye"))
    result = await cs._run_tool("delete_todo", {"todo_id": str(created.id)})
    assert "Deleted" in result


async def test_run_tool_delete_todo_not_found(patched_session: AsyncSession) -> None:
    result = await cs._run_tool("delete_todo", {"todo_id": str(uuid4())})
    assert "not found" in result


async def test_run_tool_clear_completed(patched_session: AsyncSession) -> None:
    await todo_service.create_todo(patched_session, TodoCreate(title="Active"))
    await todo_service.create_todo(patched_session, TodoCreate(title="Done1", is_completed=True))
    await todo_service.create_todo(patched_session, TodoCreate(title="Done2", is_completed=True))
    result = await cs._run_tool("clear_completed", {})
    assert "2" in result


async def test_run_tool_unknown_tool(patched_session: AsyncSession) -> None:
    result = await cs._run_tool("nonexistent_tool", {})
    assert "Unknown tool" in result


# --- chat() tests ---


def _make_llm_response(
    content: str | None, finish_reason: str = "stop", tool_calls: Any = None
) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.finish_reason = finish_reason
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


async def test_chat_simple_response() -> None:
    mock_resp = _make_llm_response("Here you go!")
    with patch("app.services.chat_service.litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_resp
        result = await cs.chat("list my todos", [])
    assert result == "Here you go!"


async def test_chat_llm_error() -> None:
    with patch("app.services.chat_service.litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = Exception("timeout")
        result = await cs.chat("hello", [])
    assert "Error communicating" in result


async def test_chat_with_tool_call(patched_session: AsyncSession) -> None:
    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function.name = "list_todos"
    tool_call.function.arguments = "{}"

    tool_resp = _make_llm_response(None, finish_reason="tool_calls", tool_calls=[tool_call])
    final_resp = _make_llm_response("You have no todos.")

    with patch("app.services.chat_service.litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = [tool_resp, final_resp]
        result = await cs.chat("list my todos", [])

    assert result == "You have no todos."
    assert mock_llm.call_count == 2
