"""Tests for /api/chat/* (info, models, sessions, stream persistence)."""

import json
import re
from contextlib import suppress
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services import chat_history

# --- /api/chat/info ---


async def test_info_reports_anthropic_by_default(client: AsyncClient) -> None:
    resp = await client.get("/api/chat/info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == settings.chat_model
    assert data["provider"] in (
        "anthropic", "openai", "lm-studio", "ollama", "ollama-cloud", "unknown",
    )
    assert data["streaming"] is True
    assert isinstance(data["tool_use_supported"], bool)


async def test_info_detects_lm_studio(client: AsyncClient) -> None:
    with patch.object(settings, "chat_model", "openai/qwen2.5-7b-instruct"), patch.object(
        settings, "chat_api_base", "http://localhost:1234/v1"
    ):
        resp = await client.get("/api/chat/info")
    assert resp.json()["provider"] == "lm-studio"
    assert resp.json()["tool_use_supported"] is True


async def test_info_detects_ollama(client: AsyncClient) -> None:
    with patch.object(settings, "chat_model", "ollama/llama3.1"), patch.object(
        settings, "chat_api_base", ""
    ):
        resp = await client.get("/api/chat/info")
    assert resp.json()["provider"] == "ollama"
    assert resp.json()["tool_use_supported"] is False


async def test_info_detects_ollama_cloud(client: AsyncClient) -> None:
    with patch.object(settings, "chat_model", "ollama/llama3.3"), patch.object(
        settings, "chat_api_base", "https://api.ollama.com/api"
    ):
        resp = await client.get("/api/chat/info")
    assert resp.json()["provider"] == "ollama-cloud"
    assert resp.json()["tool_use_supported"] is False


# --- /api/chat/models ---


async def test_models_no_base_returns_unavailable(client: AsyncClient) -> None:
    with patch.object(settings, "chat_api_base", ""):
        resp = await client.get("/api/chat/models")
    data = resp.json()
    assert data["available"] is False
    assert "CHAT_API_BASE" in data["error"]


async def test_models_anthropic_returns_unavailable(client: AsyncClient) -> None:
    with patch.object(settings, "chat_api_base", "https://api.anthropic.com"), patch.object(
        settings, "chat_model", "claude-sonnet-4-6"
    ):
        resp = await client.get("/api/chat/models")
    data = resp.json()
    assert data["available"] is False
    assert "Anthropic" in data["error"]


async def test_models_proxies_openai_compatible(client: AsyncClient) -> None:
    fake_response = {
        "object": "list",
        "data": [
            {"id": "model-a", "owned_by": "user"},
            {"id": "model-b", "owned_by": "user"},
        ],
    }

    class _FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            class _R:
                def raise_for_status(self):
                    return None

                def json(self):
                    return fake_response

            return _R()

    with patch.object(settings, "chat_api_base", "http://localhost:1234/v1"), patch.object(
        settings, "chat_model", "openai/x"
    ), patch("app.routers.chat.httpx.AsyncClient", _FakeAsyncClient):
        resp = await client.get("/api/chat/models")

    data = resp.json()
    assert data["available"] is True
    assert data["provider"] == "lm-studio"
    assert [m["id"] for m in data["models"]] == ["model-a", "model-b"]


# --- /api/chat/sessions ---


async def test_sessions_create_list_delete(client: AsyncClient) -> None:
    create = await client.post("/api/chat/sessions", json={"title": "Project X"})
    assert create.status_code == 201
    sid = create.json()["id"]
    assert create.json()["title"] == "Project X"

    listing = await client.get("/api/chat/sessions")
    assert listing.status_code == 200
    assert any(s["id"] == sid for s in listing.json())

    delete = await client.delete(f"/api/chat/sessions/{sid}")
    assert delete.status_code == 204

    missing = await client.get(f"/api/chat/sessions/{sid}")
    assert missing.status_code == 404


async def test_sessions_list_messages(client: AsyncClient) -> None:
    create = await client.post("/api/chat/sessions")
    sid = create.json()["id"]
    # Add a message directly via the service (the chat endpoint also persists)
    # but the API doesn't expose a direct add endpoint; this is a sanity check.
    from app.database import async_session_factory

    async with async_session_factory() as db:
        await chat_history.add_message(db, __import__("uuid").UUID(sid), "user", "hi")

    msgs = await client.get(f"/api/chat/sessions/{sid}/messages")
    assert msgs.status_code == 200
    payload = msgs.json()
    assert len(payload) == 1
    assert payload[0]["role"] == "user"
    assert payload[0]["content"] == "hi"


# --- /api/chat/ persistence (non-streaming) ---


async def test_chat_persists_when_session_id_given(
    client: AsyncClient, session: AsyncSession
) -> None:
    create = await client.post("/api/chat/sessions")
    sid = create.json()["id"]

    with patch(
        "app.services.chat_service.chat", new_callable=AsyncMock
    ) as mock_chat:
        mock_chat.return_value = ("Hello back!", [])
        resp = await client.post(
            "/api/chat/", json={"message": "hi", "session_id": sid}
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["response"] == "Hello back!"
    assert body["session_id"] == sid

    # Verify persistence
    listing = await client.get(f"/api/chat/sessions/{sid}/messages")
    msgs = listing.json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == "hi"
    assert msgs[1]["content"] == "Hello back!"


async def test_chat_persists_tool_turns(
    client: AsyncClient, session: AsyncSession
) -> None:
    create = await client.post("/api/chat/sessions")
    sid = create.json()["id"]

    with patch(
        "app.services.chat_service.chat", new_callable=AsyncMock
    ) as mock_chat:
        mock_chat.return_value = (
            "All done",
            [{"role": "tool", "tool_call_id": "c1", "content": "[]"}],
        )
        resp = await client.post(
            "/api/chat/", json={"message": "list", "session_id": sid}
        )
    assert resp.status_code == 200

    listing = await client.get(f"/api/chat/sessions/{sid}/messages")
    msgs = listing.json()
    # user, tool result, assistant final
    assert [m["role"] for m in msgs] == ["user", "tool", "assistant"]
    assert msgs[1]["tool_call_id"] == "c1"


async def test_chat_unknown_session_returns_404(client: AsyncClient) -> None:
    import uuid

    with patch(
        "app.services.chat_service.chat", new_callable=AsyncMock
    ) as mock_chat:
        mock_chat.return_value = ("ok", [])
        resp = await client.post(
            "/api/chat/", json={"message": "x", "session_id": str(uuid.uuid4())}
        )
    assert resp.status_code == 404


# --- /api/chat/stream (SSE) ---


async def test_stream_emits_token_and_done_with_delta_key(
    client: AsyncClient,
) -> None:
    """Regression: stream must use ``delta`` (not ``content``) for tokens
    and ``response`` for the final answer, so the JS consumer's
    ``ev.content || ev.delta`` branch always finds the field.
    """

    async def fake_stream(message, history):
        yield {"type": "token", "delta": "Hello "}
        yield {"type": "token", "delta": "world"}
        yield {"type": "done", "response": "Hello world", "intermediate": []}

    with patch("app.services.chat_service.chat_stream", side_effect=fake_stream):
        resp = await client.post("/api/chat/stream", json={"message": "hi"})

    assert resp.status_code == 200
    body = resp.text
    assert 'event: token' in body
    assert '"delta": "Hello "' in body
    assert '"delta": "world"' in body
    assert 'event: done' in body
    assert '"response": "Hello world"' in body


async def test_stream_done_response_is_final_text(client: AsyncClient) -> None:
    """The done event's ``response`` is the canonical final text — even if
    earlier tokens included pre-tool chatter. JS commits ``ev.response``
    when present to avoid showing only the post-tool continuation.
    """

    async def fake_stream(message, history):
        yield {"type": "token", "delta": "Calling tool..."}
        yield {
            "type": "tool",
            "name": "list_todos",
            "arguments": {},
            "result": "[]",
            "persist": [],
        }
        yield {"type": "token", "delta": "Empty list."}
        yield {"type": "done", "response": "Your list is empty.", "intermediate": []}

    with patch("app.services.chat_service.chat_stream", side_effect=fake_stream):
        resp = await client.post("/api/chat/stream", json={"message": "list"})

    assert resp.status_code == 200
    # The final done.response must be the value the client should render.
    assert '"response": "Your list is empty."' in resp.text


async def test_stream_persists_turn_with_final_response(
    client: AsyncClient,
) -> None:
    """Regression: when chat_stream finishes with a done.response that
    differs from the streamed token buffer, the persisted assistant
    message must equal the final response, not the partial token buffer.
    """

    create = await client.post("/api/chat/sessions")
    sid = create.json()["id"]

    async def fake_stream(message, history):
        yield {"type": "token", "delta": "Pre-tool chatter."}
        yield {
            "type": "tool",
            "name": "create_todo",
            "arguments": {"title": "x"},
            "result": "ok",
            "persist": [
                {
                    "role": "assistant",
                    "content": "Pre-tool chatter.",
                    "tool_calls": [],
                },
                {"role": "tool", "tool_call_id": "t1", "content": "ok"},
            ],
        }
        yield {"type": "done", "response": "Created x.", "intermediate": []}

    with patch("app.services.chat_service.chat_stream", side_effect=fake_stream):
        resp = await client.post(
            "/api/chat/stream", json={"message": "create", "session_id": sid}
        )

    assert resp.status_code == 200
    msgs = (await client.get(f"/api/chat/sessions/{sid}/messages")).json()
    assert msgs[-1]["role"] == "assistant"
    assert msgs[-1]["content"] == "Created x."


async def test_stream_frames_are_single_newline_terminated(
    client: AsyncClient,
) -> None:
    """Regression: each SSE event must end with exactly one ``\\n`` (not
    ``\\n\\n``). Uvicorn doesn't add a trailing newline to chunked body
    writes, and an extra ``\\n`` produces a blank ``data:`` line in the
    next frame's buffer, causing line-based SSE parsers to drop events.
    """

    async def fake_stream(message, history):
        yield {"type": "token", "delta": "A"}
        yield {"type": "token", "delta": "B"}
        yield {"type": "done", "response": "AB", "intermediate": []}

    with patch("app.services.chat_service.chat_stream", side_effect=fake_stream):
        resp = await client.post("/api/chat/stream", json={"message": "x"})

    body = resp.text
    # Every event line should be exactly one trailing newline.
    # No frame should be terminated by a blank line.
    assert "\n\n" not in body, body
    # All three events present, in order, each with a single trailing \n.
    assert body.count("event: token\n") == 2
    assert body.count("event: done\n") == 1


async def test_stream_consumer_parses_all_events_with_single_newline(
    client: AsyncClient,
) -> None:
    """End-to-end SSE parsing: simulate the browser's consumer against the
    real stream and assert every event fires exactly once. The previous
    parser that required a blank line dropped events because the wire
    format uses a single ``\\n`` terminator per frame.
    """

    async def fake_stream(message, history):
        yield {"type": "start", "session_id": None, "model": "m", "provider": "p"}
        yield {"type": "token", "delta": "Hello"}
        yield {"type": "token", "delta": " world"}
        yield {"type": "tool", "name": "list_todos", "arguments": {}, "result": "[]"}
        yield {"type": "done", "response": "Hello world", "intermediate": []}

    # Mirrors the rewritten index.html ``consumeSSE`` — accepts both
    # spec-compliant blank-line frames and Uvicorn's single-``\\n``-per-frame
    # format. The ``(?=\\nevent:)`` lookahead treats a new ``event:`` line
    # as the start of the next frame even when there was no blank line.
    def parse_sse(body: str) -> list[dict]:
        events: list[dict] = []
        for frame in re.split(r"\n\n|(?=\nevent:)", body):
            if not frame.strip():
                continue
            event = "message"
            data_lines: list[str] = []
            for line in frame.split("\n"):
                if not line or line.startswith(":"):
                    continue
                idx = line.indexOf(":") if hasattr(line, "indexOf") else line.find(":")
                if idx < 0:
                    continue
                field = line[:idx]
                value = line[idx + 1 :]
                if value.startswith(" "):
                    value = value[1:]
                if field == "event":
                    event = value
                elif field == "data":
                    data_lines.append(value)
            if not data_lines:
                continue
            with suppress(json.JSONDecodeError):
                parsed = json.loads("\n".join(data_lines))
                parsed["_event"] = event
                events.append(parsed)
        return events

    with patch("app.services.chat_service.chat_stream", side_effect=fake_stream):
        resp = await client.post("/api/chat/stream", json={"message": "x"})

    received = parse_sse(resp.text)
    # 1 start + 2 token + 1 tool + 1 done — every event the producer
    # emitted must be parsed exactly once.
    assert len(received) == 5, received
    assert received[0]["_event"] == "start"
    assert received[1]["_event"] == "token" and received[1]["delta"] == "Hello"
    assert received[2]["_event"] == "token" and received[2]["delta"] == " world"
    assert received[3]["_event"] == "tool" and received[3]["name"] == "list_todos"
    assert received[4]["_event"] == "done" and received[4]["response"] == "Hello world"
