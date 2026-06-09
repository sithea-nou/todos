"""Tests for the chat_service layer."""

import json
import os
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
async def patched_session(session: AsyncSession) -> AsyncGenerator[AsyncSession]:
    """Patch chat_service to use the test DB session."""

    @asynccontextmanager
    async def _factory() -> AsyncGenerator[AsyncSession]:
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
        result, intermediate = await cs.chat("list my todos", [])
    assert result == "Here you go!"
    assert intermediate == []


async def test_chat_llm_error() -> None:
    with patch("app.services.chat_service.litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = Exception("timeout")
        result, _ = await cs.chat("hello", [])
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
        result, intermediate = await cs.chat("list my todos", [])

    assert result == "You have no todos."
    assert mock_llm.call_count == 2
    # Intermediate should contain one assistant turn + one tool result
    assert len(intermediate) == 2
    assert intermediate[0]["role"] == "assistant"
    assert intermediate[0]["tool_calls"][0]["function"]["name"] == "list_todos"
    assert intermediate[1]["role"] == "tool"
    assert intermediate[1]["tool_call_id"] == "call_1"


# --- chat_stream() tests ---


class _FakeDelta:
    def __init__(self, content=None, tool_calls=None, role=None):
        self.content = content
        self.tool_calls = tool_calls
        self.role = role


class _FakeToolCall:
    def __init__(self, index=0, id=None, name=None, arguments=None):
        self.index = index
        self.id = id
        self.function = type("Fn", (), {"name": name, "arguments": arguments})()


class _FakeChoice:
    def __init__(self, delta, finish_reason=None):
        self.delta = delta
        self.finish_reason = finish_reason


class _FakeChunk:
    def __init__(self, delta=None, finish_reason=None, tool_calls=None):
        if delta is None:
            delta = _FakeDelta(content=None, tool_calls=tool_calls)
        self.choices = [_FakeChoice(delta, finish_reason)]


class _FakeAsyncStream:
    """Async-iterable wrapper around a list of chunks."""

    def __init__(self, chunks):
        self._chunks = chunks
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._idx]
        self._idx += 1
        return chunk


async def test_chat_stream_yields_tokens_and_done() -> None:
    chunks = [
        _FakeChunk(delta=_FakeDelta(content="Hello", role="assistant")),
        _FakeChunk(delta=_FakeDelta(content=" world")),
        _FakeChunk(delta=_FakeDelta(content=""), finish_reason="stop"),
    ]
    fake_stream = _FakeAsyncStream(chunks)

    with patch("app.services.chat_service.litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = fake_stream
        events = []
        async for evt in cs.chat_stream("hi", []):
            events.append(evt)

    assert events[0]["type"] == "token"
    assert events[0]["delta"] == "Hello"
    assert events[1]["delta"] == " world"
    done = [e for e in events if e["type"] == "done"][-1]
    assert done["response"] == "Hello world"


async def test_chat_stream_emits_tool_event(patched_session: AsyncSession) -> None:
    tool_chunks = [
        _FakeChunk(
            delta=_FakeDelta(
                tool_calls=[_FakeToolCall(index=0, id="t1", name="list_todos", arguments="{}")],
                role="assistant",
            )
        ),
        _FakeChunk(delta=_FakeDelta(content=""), finish_reason="tool_calls"),
    ]
    final_text_chunks = [
        _FakeChunk(delta=_FakeDelta(content="Done", role="assistant")),
        _FakeChunk(delta=_FakeDelta(content=""), finish_reason="stop"),
    ]

    fake_streams = [_FakeAsyncStream(tool_chunks), _FakeAsyncStream(final_text_chunks)]

    with patch("app.services.chat_service.litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = fake_streams
        events = []
        async for evt in cs.chat_stream("list my todos", []):
            events.append(evt)

    tool_events = [e for e in events if e["type"] == "tool"]
    assert tool_events, f"expected at least one tool event, got {events}"
    assert tool_events[0]["name"] == "list_todos"
    done = [e for e in events if e["type"] == "done"][-1]
    assert done["response"] == "Done"


async def test_chat_stream_parses_ollama_json_in_text(
    patched_session: AsyncSession,
) -> None:
    """Ollama (streaming) may emit tool calls as plain JSON text
    instead of native tool_calls deltas."""
    # First iteration: model returns tool call as text token
    first_chunks = [
        _FakeChunk(
            delta=_FakeDelta(
                content='{"name": "list_todos", "arguments": {}}'
            ),
            finish_reason="stop",
        ),
    ]
    # Second iteration: model answers with tool results
    second_chunks = [
        _FakeChunk(delta=_FakeDelta(content="Here are your todos")),
        _FakeChunk(delta=_FakeDelta(content=""), finish_reason="stop"),
    ]

    fake_streams = [_FakeAsyncStream(first_chunks), _FakeAsyncStream(second_chunks)]

    with patch("app.services.chat_service.litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = fake_streams
        events = []
        async for evt in cs.chat_stream("list my todos", []):
            events.append(evt)

    tool_events = [e for e in events if e["type"] == "tool"]
    assert tool_events, f"expected at least one tool event, got {events}"
    assert tool_events[0]["name"] == "list_todos"
    # The JSON text should NOT appear as the final response
    done = [e for e in events if e["type"] == "done"][-1]
    assert done["response"] == "Here are your todos"


# --- _setup_env tests (LM Studio dummy key workaround) ---


def _clear_litellm_keys() -> None:
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OLLAMA_API_KEY"):
        os.environ.pop(key, None)


def test_setup_env_injects_dummy_key_for_local_openai_provider() -> None:
    """When CHAT_MODEL is openai/* and no key is set, inject a dummy key."""
    _clear_litellm_keys()
    with patch.object(cs.settings, "openai_api_key", ""), patch.object(
        cs.settings, "anthropic_api_key", ""
    ), patch.object(cs.settings, "chat_api_base", "http://localhost:1234/v1"), patch.object(
        cs.settings, "chat_model", "openai/qwen2.5-7b-instruct"
    ):
        cs._setup_env()
    assert os.environ.get("OPENAI_API_KEY") == "lm-studio"


def test_setup_env_injects_dummy_key_for_localhost_base() -> None:
    """A localhost CHAT_API_BASE alone is enough to trigger the dummy key."""
    _clear_litellm_keys()
    with patch.object(cs.settings, "openai_api_key", ""), patch.object(
        cs.settings, "anthropic_api_key", ""
    ), patch.object(cs.settings, "chat_api_base", "http://127.0.0.1:1234/v1"), patch.object(
        cs.settings, "chat_model", "custom-model"
    ):
        cs._setup_env()
    assert os.environ.get("OPENAI_API_KEY") == "lm-studio"


def test_setup_env_does_not_inject_when_remote() -> None:
    """Remote API bases (no local host marker, no openai/ prefix) stay untouched."""
    _clear_litellm_keys()
    with patch.object(cs.settings, "openai_api_key", ""), patch.object(
        cs.settings, "anthropic_api_key", ""
    ), patch.object(cs.settings, "chat_api_base", "https://api.example.com/v1"), patch.object(
        cs.settings, "chat_model", "custom-model"
    ):
        cs._setup_env()
    assert "OPENAI_API_KEY" not in os.environ


def test_setup_env_preserves_explicit_key() -> None:
    """A user-supplied OPENAI_API_KEY (via settings.openai_api_key) wins."""
    _clear_litellm_keys()
    with patch.object(cs.settings, "openai_api_key", "sk-real-key"), patch.object(
        cs.settings, "anthropic_api_key", ""
    ), patch.object(cs.settings, "chat_api_base", ""), patch.object(
        cs.settings, "chat_model", "gpt-4o"
    ):
        cs._setup_env()
    assert os.environ.get("OPENAI_API_KEY") == "sk-real-key"


def test_setup_env_sets_ollama_api_key() -> None:
    """A user-supplied OLLAMA_API_KEY is exported for LiteLLM."""
    _clear_litellm_keys()
    with patch.object(cs.settings, "openai_api_key", ""), patch.object(
        cs.settings, "anthropic_api_key", ""
    ), patch.object(cs.settings, "ollama_api_key", "oc-sk-123"), patch.object(
        cs.settings, "chat_model", "ollama/llama3.3"
    ):
        cs._setup_env()
    assert os.environ.get("OLLAMA_API_KEY") == "oc-sk-123"
