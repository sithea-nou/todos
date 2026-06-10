"""Tests for the chat_service layer.

Tool execution now routes through the MCP server, so these tests
verify the same operations via ``_run_tool_via_mcp``.
"""

import json
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

import app.mcp_server
import app.services.chat_service as cs
from app.models.todo import TodoCreate
from app.services import todo_service


@pytest_asyncio.fixture
async def patched_session(session: AsyncSession) -> AsyncGenerator[AsyncSession]:
    """Patch MCP server's session factory so _run_tool_via_mcp uses the test DB."""

    @asynccontextmanager
    async def _factory() -> AsyncGenerator[AsyncSession]:
        yield session

    original = app.mcp_server.async_session_factory
    app.mcp_server.async_session_factory = _factory  # type: ignore[assignment]
    # Reset the cached OpenAI tools so tests pick up the MCP server fresh
    cs._cached_openai_tools = None
    yield session
    app.mcp_server.async_session_factory = original  # type: ignore[assignment]


# --- _run_tool_via_mcp tests ---


async def test_run_tool_list_todos_empty(patched_session: AsyncSession) -> None:
    result = await cs._run_tool_via_mcp("list_todos", {})
    assert json.loads(result) == []


async def test_run_tool_list_todos(patched_session: AsyncSession) -> None:
    await todo_service.create_todo(patched_session, TodoCreate(title="A"))
    await todo_service.create_todo(patched_session, TodoCreate(title="B"))
    result = await cs._run_tool_via_mcp("list_todos", {})
    assert len(json.loads(result)) == 2


async def test_run_tool_list_todos_filter_completed(patched_session: AsyncSession) -> None:
    await todo_service.create_todo(patched_session, TodoCreate(title="Active"))
    await todo_service.create_todo(patched_session, TodoCreate(title="Done", is_completed=True))
    result = await cs._run_tool_via_mcp("list_todos", {"completed": True})
    todos = json.loads(result)
    assert len(todos) == 1
    assert todos[0]["title"] == "Done"


async def test_run_tool_list_todos_order_by(patched_session: AsyncSession) -> None:
    await todo_service.create_todo(patched_session, TodoCreate(title="Low", priority=1))
    await todo_service.create_todo(patched_session, TodoCreate(title="High", priority=3))
    result = await cs._run_tool_via_mcp("list_todos", {"order_by": "priority"})
    todos = json.loads(result)
    assert len(todos) == 2
    assert todos[0]["priority"] >= todos[1]["priority"]


async def test_run_tool_create_todo(patched_session: AsyncSession) -> None:
    result = await cs._run_tool_via_mcp(
        "create_todo", {"title": "New task", "description": "Details"}
    )
    data = json.loads(result)
    assert data["title"] == "New task"
    assert data["description"] == "Details"
    assert data["is_completed"] is False


async def test_run_tool_create_todo_with_priority_and_due_date(
    patched_session: AsyncSession,
) -> None:
    result = await cs._run_tool_via_mcp(
        "create_todo", {"title": "Important", "priority": 3, "due_date": "2026-07-15"}
    )
    data = json.loads(result)
    assert data["priority"] == 3
    assert data["due_date"] == "2026-07-15"


async def test_run_tool_get_todo(patched_session: AsyncSession) -> None:
    created = await todo_service.create_todo(patched_session, TodoCreate(title="Find me"))
    result = await cs._run_tool_via_mcp("get_todo", {"todo_id": str(created.id)})
    assert json.loads(result)["title"] == "Find me"


async def test_run_tool_get_todo_not_found(patched_session: AsyncSession) -> None:
    result = await cs._run_tool_via_mcp("get_todo", {"todo_id": str(uuid4())})
    assert "not found" in result


async def test_run_tool_get_todo_invalid_uuid(patched_session: AsyncSession) -> None:
    result = await cs._run_tool_via_mcp("get_todo", {"todo_id": "not-a-uuid"})
    assert "Invalid" in result


async def test_run_tool_update_todo(patched_session: AsyncSession) -> None:
    created = await todo_service.create_todo(patched_session, TodoCreate(title="Old"))
    result = await cs._run_tool_via_mcp(
        "update_todo",
        {"todo_id": str(created.id), "title": "New", "is_completed": True},
    )
    data = json.loads(result)
    assert data["title"] == "New"
    assert data["is_completed"] is True


async def test_run_tool_update_todo_priority_and_due_date(
    patched_session: AsyncSession,
) -> None:
    created = await todo_service.create_todo(patched_session, TodoCreate(title="Task"))
    result = await cs._run_tool_via_mcp(
        "update_todo",
        {"todo_id": str(created.id), "priority": 2, "due_date": "2026-08-01"},
    )
    data = json.loads(result)
    assert data["priority"] == 2
    assert data["due_date"] == "2026-08-01"


async def test_run_tool_update_todo_clear_due_date(patched_session: AsyncSession) -> None:
    created = await todo_service.create_todo(
        patched_session, TodoCreate(title="Task", due_date="2026-08-01")
    )
    result = await cs._run_tool_via_mcp(
        "update_todo",
        {"todo_id": str(created.id), "due_date": "clear"},
    )
    data = json.loads(result)
    assert data["due_date"] is None


async def test_run_tool_update_todo_not_found(patched_session: AsyncSession) -> None:
    result = await cs._run_tool_via_mcp("update_todo", {"todo_id": str(uuid4()), "title": "X"})
    assert "not found" in result


async def test_run_tool_delete_todo(patched_session: AsyncSession) -> None:
    created = await todo_service.create_todo(patched_session, TodoCreate(title="Bye"))
    result = await cs._run_tool_via_mcp("delete_todo", {"todo_id": str(created.id)})
    assert "Deleted" in result


async def test_run_tool_delete_todo_not_found(patched_session: AsyncSession) -> None:
    result = await cs._run_tool_via_mcp("delete_todo", {"todo_id": str(uuid4())})
    assert "not found" in result


async def test_run_tool_clear_completed(patched_session: AsyncSession) -> None:
    await todo_service.create_todo(patched_session, TodoCreate(title="Active"))
    await todo_service.create_todo(patched_session, TodoCreate(title="Done1", is_completed=True))
    await todo_service.create_todo(patched_session, TodoCreate(title="Done2", is_completed=True))
    result = await cs._run_tool_via_mcp("clear_completed", {})
    assert "2" in result


async def test_run_tool_reorder_todos(patched_session: AsyncSession) -> None:
    t1 = await todo_service.create_todo(patched_session, TodoCreate(title="A"))
    t2 = await todo_service.create_todo(patched_session, TodoCreate(title="B"))
    result = await cs._run_tool_via_mcp(
        "reorder_todos",
        {"items": [{"id": str(t2.id), "position": 0}, {"id": str(t1.id), "position": 1}]},
    )
    data = json.loads(result)
    assert len(data) >= 2


async def test_run_tool_unknown_tool(patched_session: AsyncSession) -> None:
    result = await cs._run_tool_via_mcp("nonexistent_tool", {})
    assert "nonexistent_tool" in result


# --- _build_openai_tools tests ---


async def test_build_openai_tools_includes_all_tools(patched_session: AsyncSession) -> None:
    cs._cached_openai_tools = None
    tools = await cs._build_openai_tools()
    names = [t["function"]["name"] for t in tools]
    assert "list_todos" in names
    assert "create_todo" in names
    assert "update_todo" in names
    assert "delete_todo" in names
    assert "get_todo" in names
    assert "clear_completed" in names
    assert "reorder_todos" in names


async def test_build_openai_tools_has_priority_and_due_date(
    patched_session: AsyncSession,
) -> None:
    cs._cached_openai_tools = None
    tools = await cs._build_openai_tools()
    create_fn = next(t for t in tools if t["function"]["name"] == "create_todo")
    props = create_fn["function"]["parameters"]["properties"]
    assert "priority" in props
    assert "due_date" in props

    update_fn = next(t for t in tools if t["function"]["name"] == "update_todo")
    props = update_fn["function"]["parameters"]["properties"]
    assert "priority" in props
    assert "due_date" in props


async def test_build_openai_tools_no_anyof(patched_session: AsyncSession) -> None:
    """OpenAI function calling doesn't support anyOf — schemas must be flattened."""
    cs._cached_openai_tools = None
    tools = await cs._build_openai_tools()
    for t in tools:
        schema_str = json.dumps(t["function"]["parameters"])
        assert "anyOf" not in schema_str, f"anyOf found in {t['function']['name']}"


# --- _mcp_schema_to_openai tests ---


def test_flatten_anyof_string_or_null() -> None:
    result = cs._flatten_anyof({
        "anyOf": [{"type": "string"}, {"type": "null"}],
        "description": "Optional desc",
        "default": None,
    })
    assert result == {"type": "string", "description": "Optional desc", "default": None}


def test_flatten_anyof_integer_or_null() -> None:
    result = cs._flatten_anyof({
        "anyOf": [{"type": "integer"}, {"type": "null"}],
        "default": None,
    })
    assert result == {"type": "integer", "default": None}


def test_flatten_anyof_passthrough_plain_type() -> None:
    result = cs._flatten_anyof({"type": "string", "description": "A field"})
    assert result == {"type": "string", "description": "A field"}


def test_mcp_schema_to_openai_strips_additional_properties() -> None:
    result = cs._mcp_schema_to_openai({
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string", "description": "Title"},
        },
        "required": ["title"],
    })
    assert "additionalProperties" not in result
    assert "title" in result["properties"]
    assert result["required"] == ["title"]


def test_mcp_schema_to_openai_flattens_anyof_in_items() -> None:
    result = cs._mcp_schema_to_openai({
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "additionalProperties": True,
                    "type": "object",
                },
                "description": "List of items",
            }
        },
        "required": ["items"],
    })
    items = result["properties"]["items"]
    assert items["type"] == "array"
    assert items["items"] == {"type": "object"}


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
