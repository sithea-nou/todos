"""Chat router: streaming + non-streaming /api/chat/, /api/chat/info, /api/chat/models."""

import json
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.services import chat_history, chat_service

router = APIRouter()


# ---------- Schemas ----------


class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, Any]] = []
    session_id: UUID | None = None  # when set, persist + load from DB
    stream: bool = False  # kept for API parity; /stream endpoint is the SSE one


class ChatResponse(BaseModel):
    response: str
    session_id: UUID | None = None


class ChatInfo(BaseModel):
    provider: str
    model: str
    api_base: str
    streaming: bool
    tool_use_supported: bool


class ModelInfo(BaseModel):
    id: str
    owned_by: str | None = None


class ModelsResponse(BaseModel):
    provider: str
    api_base: str
    models: list[ModelInfo]
    available: bool
    error: str | None = None


# ---------- Provider detection ----------


def _detect_provider() -> str:
    """Best-effort provider name from CHAT_MODEL + CHAT_API_BASE."""
    model = settings.chat_model.lower()
    base = (settings.chat_api_base or "").lower()
    if model.startswith("ollama/"):
        if "api.ollama.com" in base or "ollama.com" in base:
            return "ollama-cloud"
        return "ollama"
    if model.startswith("openai/"):
        if any(h in base for h in ("localhost", "127.0.0.1", "host.docker.internal", "0.0.0.0")):
            return "lm-studio"
        return "openai-compatible"
    if model.startswith("anthropic/") or "claude" in model:
        return "anthropic"
    if model.startswith("gpt-") or "openai" in model:
        return "openai"
    if not settings.chat_api_base:
        if settings.anthropic_api_key:
            return "anthropic"
        if settings.openai_api_key:
            return "openai"
    return "unknown"


def _supports_native_tool_use() -> bool:
    """Heuristic: Ollama (local or cloud) is known to be unreliable for function calling."""
    return _detect_provider() not in ("ollama", "ollama-cloud")


# ---------- /api/chat/info ----------


@router.get("/info", response_model=ChatInfo)
async def chat_info() -> ChatInfo:
    """Return the active chat provider, model, and capability flags."""
    return ChatInfo(
        provider=_detect_provider(),
        model=settings.chat_model,
        api_base=settings.chat_api_base or "",
        streaming=True,
        tool_use_supported=_supports_native_tool_use(),
    )


# ---------- /api/chat/models ----------


@router.get("/models", response_model=ModelsResponse)
async def list_chat_models() -> ModelsResponse:
    """List models exposed by the configured OpenAI-compatible server.

    For LM Studio / vLLM / Ollama (with OpenAI shim) this proxies
    ``GET {api_base}/models``. Anthropic and other providers that don't
    expose a /models endpoint return ``available=False`` with an explanation.
    """
    base = settings.chat_api_base.rstrip("/") if settings.chat_api_base else ""
    provider = _detect_provider()

    if not base:
        return ModelsResponse(
            provider=provider,
            api_base="",
            models=[],
            available=False,
            error="No CHAT_API_BASE configured; cannot enumerate models.",
        )

    if provider == "anthropic":
        return ModelsResponse(
            provider=provider,
            api_base=base,
            models=[],
            available=False,
            error="Anthropic does not expose a /models endpoint here.",
        )

    url = f"{base}/models"
    api_key = settings.openai_api_key or settings.anthropic_api_key or "lm-studio"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            payload = r.json()
    except httpx.HTTPError as exc:
        return ModelsResponse(
            provider=provider,
            api_base=base,
            models=[],
            available=False,
            error=f"Failed to reach {url}: {exc.__class__.__name__}: {exc}",
        )
    except Exception as exc:
        return ModelsResponse(
            provider=provider,
            api_base=base,
            models=[],
            available=False,
            error=f"Unexpected error: {exc}",
        )

    raw_models = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw_models, list):
        return ModelsResponse(
            provider=provider,
            api_base=base,
            models=[],
            available=False,
            error="Server returned an unexpected /models payload shape.",
        )

    models = [
        ModelInfo(id=str(m.get("id", "")), owned_by=m.get("owned_by"))
        for m in raw_models
        if isinstance(m, dict) and m.get("id")
    ]
    return ModelsResponse(
        provider=provider, api_base=base, models=models, available=True
    )


# ---------- /api/chat/ ----------


async def _persist_turn(
    session_id: UUID | None,
    user_message: str,
    assistant_text: str,
    intermediate: list[dict[str, Any]] | None = None,
) -> UUID | None:
    """Persist a user message + assistant final text + any tool turns."""
    if session_id is None:
        return None
    from app.database import async_session_factory

    async with async_session_factory() as db:
        existing = await chat_history.get_session_or_none(db, session_id)
        if existing is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Chat session {session_id} not found. Create one via "
                    "POST /api/chat/sessions first."
                ),
            )
        await chat_history.add_message(db, session_id, "user", user_message)
        for turn in intermediate or []:
            await chat_history.add_message(
                db,
                session_id,
                turn["role"],
                turn.get("content", ""),
                tool_calls=turn.get("tool_calls"),
                tool_call_id=turn.get("tool_call_id"),
            )
        await chat_history.add_message(db, session_id, "assistant", assistant_text)
    return session_id


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Non-streaming chat. Persists the turn if ``session_id`` is provided."""
    history = request.history
    if request.session_id is not None:
        from app.database import async_session_factory

        async with async_session_factory() as db:
            persisted = await chat_history.list_messages(db, request.session_id)
        if persisted:
            history = chat_history.messages_to_history(persisted)

    reply, intermediate = await chat_service.chat(
        message=request.message, history=history
    )
    await _persist_turn(
        request.session_id, request.message, reply, intermediate
    )
    return ChatResponse(response=reply, session_id=request.session_id)


# ---------- /api/chat/stream (SSE) ----------


def _sse(event: str, data: Any) -> str:
    """Format a Server-Sent Event frame.

    Each frame is exactly one ``event:`` line + one ``data:`` line, terminated
    by a single ``\\n``. Uvicorn/FastAPI's StreamingResponse appends no extra
    newlines, so ``\\n\\n`` would create a blank line in the wire stream and
    confuse line-based SSE parsers.
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n"


@router.post("/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """Stream the assistant reply via Server-Sent Events.

    Event types:
      - ``start`` : { session_id, model, provider }
      - ``token`` : { delta }   — incremental text
      - ``tool``  : { name, arguments, result }
      - ``done``  : { response, session_id }
      - ``error`` : { message }
    """

    async def event_gen() -> AsyncGenerator[str]:
        history = request.history
        if request.session_id is not None:
            from app.database import async_session_factory

            async with async_session_factory() as db:
                existing = await chat_history.get_session_or_none(
                    db, request.session_id
                )
                if existing is None:
                    yield _sse("error", {"message": "Chat session not found"})
                    return
                persisted = await chat_history.list_messages(db, request.session_id)
            if persisted:
                history = chat_history.messages_to_history(persisted)

        yield _sse(
            "start",
            {
                "session_id": str(request.session_id) if request.session_id else None,
                "model": settings.chat_model,
                "provider": _detect_provider(),
            },
        )

        final_text = ""
        intermediate: list[dict[str, Any]] = []
        try:
            async for event in chat_service.chat_stream(
                message=request.message, history=history
            ):
                kind = event["type"]
                if kind == "token":
                    final_text += event["delta"]
                    yield _sse("token", {"delta": event["delta"]})
                elif kind == "tool":
                    yield _sse(
                        "tool",
                        {
                            "name": event["name"],
                            "arguments": event["arguments"],
                            "result": event["result"],
                        },
                    )
                    intermediate.extend(event.get("persist", []))
                elif kind == "done":
                    final_text = event.get("response", final_text)
                    if event.get("intermediate"):
                        # Some events (e.g. tool calls) carry intermediate
                        # turns we haven't seen yet.
                        seen_ids = {(m.get("tool_call_id"), m.get("role")) for m in intermediate}
                        for m in event["intermediate"]:
                            key = (m.get("tool_call_id"), m.get("role"))
                            if key not in seen_ids:
                                intermediate.append(m)
                                seen_ids.add(key)
                elif kind == "error":
                    yield _sse("error", {"message": event["message"]})
                    return
        except Exception as exc:
            yield _sse("error", {"message": str(exc)})
            return

        if request.session_id is not None:
            try:
                await _persist_turn(
                    request.session_id,
                    request.message,
                    final_text,
                    intermediate,
                )
            except HTTPException as exc:
                yield _sse("error", {"message": exc.detail})
                return
            except Exception as exc:
                yield _sse("error", {"message": f"Persistence failed: {exc}"})
                return

        yield _sse(
            "done",
            {
                "response": final_text,
                "session_id": str(request.session_id) if request.session_id else None,
            },
        )

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

