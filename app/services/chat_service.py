"""Chat service: LLM agent with todo tool use.

Supports any provider via LiteLLM:
  - Anthropic  → CHAT_MODEL=claude-sonnet-4-6    + ANTHROPIC_API_KEY
  - OpenAI     → CHAT_MODEL=gpt-4o               + OPENAI_API_KEY
  - Ollama     → CHAT_MODEL=ollama/llama3.1       (CHAT_API_BASE defaults to localhost)
  - Any OpenAI-compatible server:
                 CHAT_MODEL=openai/my-model        + CHAT_API_BASE=http://host:port/v1
"""

import json
import logging
import os
from typing import Any
from uuid import UUID

import litellm

from app.config import settings
from app.database import async_session_factory
from app.models.todo import TodoCreate, TodoUpdate
from app.services import todo_service

logger = logging.getLogger(__name__)
os.environ.setdefault("LITELLM_LOG", "DEBUG")


def _try_parse_ollama_tool_calls(text: str) -> list[dict[str, Any]]:
    """Best-effort parse of tool calls from a model's text output (Ollama fallback).

    Returns a list of ``{"name": str, "arguments": dict}`` dicts.
    Handles three Ollama output patterns:

    1. Single JSON object: ``{"name": "...", "arguments": {...}}``
    2. JSON array: ``[{"name": "...", ...}, ...]``
    3. Multiple JSON objects on separate lines (newline-delimited)
    """
    if not text:
        return []
    json_str = text
    if "```json" in json_str:
        try:
            json_str = json_str.split("```json", 1)[1].split("```", 1)[0].strip()
        except IndexError:
            return []
    elif "```" in json_str:
        try:
            json_str = json_str.split("```", 1)[1].split("```", 1)[0].strip()
        except IndexError:
            return []

    # Try parsing as a single JSON value first (object or array)
    try:
        parsed = json.loads(json_str)
        results: list[dict[str, Any]] = []
        if isinstance(parsed, dict):
            results.extend(_extract_tool_calls_from_dict(parsed))
        elif isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    results.extend(_extract_tool_calls_from_dict(item))
        return results
    except json.JSONDecodeError:
        pass

    # Fall back to newline-delimited JSON objects
    results = []
    for line in json_str.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                results.extend(_extract_tool_calls_from_dict(parsed))
        except json.JSONDecodeError:
            continue
    return results


def _extract_tool_calls_from_dict(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract tool call dicts from a parsed JSON object."""
    if "name" not in parsed:
        return []
    args = parsed.get("arguments") or {}
    if not isinstance(args, dict):
        args = {}
    return [{"name": str(parsed["name"]), "arguments": args}]


_SYSTEM = (
    "You are a helpful todo assistant. Use the available tools to manage the user's todos. "
    "Be concise and friendly. "
    "When you need to call a tool, output ONLY the required JSON with no other text. "
    "After receiving tool results, answer the user directly "
    "without calling additional tools unless necessary."
)

_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_todos",
            "description": "List all todos. Optionally filter by completion status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "completed": {
                        "type": "boolean",
                        "description": "True for completed, False for active, omit for all.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_todo",
            "description": "Fetch a single todo by its UUID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "string", "description": "UUID of the todo."}
                },
                "required": ["todo_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_todo",
            "description": "Create a new todo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short title."},
                    "description": {"type": "string", "description": "Optional description."},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_todo",
            "description": "Update an existing todo. Only provided fields change.",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "string", "description": "UUID of the todo."},
                    "title": {"type": "string", "description": "New title."},
                    "description": {"type": "string", "description": "New description."},
                    "is_completed": {"type": "boolean", "description": "New completion flag."},
                },
                "required": ["todo_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_todo",
            "description": "Delete a todo by its UUID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "string", "description": "UUID of the todo."}
                },
                "required": ["todo_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_completed",
            "description": "Delete all completed todos.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _setup_env() -> None:
    """Export config API keys to env vars so LiteLLM can find them.

    Local OpenAI-compatible servers (LM Studio, vLLM, etc.) don't validate the
    API key, but LiteLLM's ``openai/`` provider refuses to send a request if
    ``OPENAI_API_KEY`` is missing. When a local ``CHAT_API_BASE`` is configured
    we inject a dummy key so requests go through.
    """
    if settings.anthropic_api_key:
        os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
    if settings.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
    if settings.ollama_api_key:
        os.environ.setdefault("OLLAMA_API_KEY", settings.ollama_api_key)

    if settings.chat_api_base and "OPENAI_API_KEY" not in os.environ:
        base = settings.chat_api_base.lower()
        is_local = any(
            host in base
            for host in ("localhost", "127.0.0.1", "host.docker.internal", "0.0.0.0")
        )
        if is_local or settings.chat_model.lower().startswith("openai/"):
            os.environ["OPENAI_API_KEY"] = "lm-studio"


def _is_ollama_cloud() -> bool:
    """True when the configured provider is Ollama Cloud (remote ollama.com API)."""
    model = settings.chat_model.lower()
    base = (settings.chat_api_base or "").lower()
    return model.startswith("ollama/") and ("ollama.com" in base or "api.ollama.com" in base)


async def _run_tool(name: str, tool_input: dict[str, Any]) -> str:
    """Execute a todo tool and return a JSON string result."""
    async with async_session_factory() as session:
        if name == "list_todos":
            completed = tool_input.get("completed")
            if completed is not None and not isinstance(completed, bool):
                type_name = type(completed).__name__
                return f"Invalid completed value: expected boolean or null, got {type_name}"
            todos = await todo_service.list_todos(session, completed=completed)
            return json.dumps([t.model_dump(mode="json") for t in todos])

        if name == "get_todo":
            try:
                todo = await todo_service.get_todo(session, UUID(tool_input["todo_id"]))
            except (ValueError, KeyError) as e:
                return f"Invalid todo_id: {e!s}"
            if todo is None:
                return f"Todo {tool_input['todo_id']} not found"
            return json.dumps(todo.model_dump(mode="json"))

        if name == "create_todo":
            payload = TodoCreate(
                title=tool_input["title"],
                description=tool_input.get("description"),
            )
            todo = await todo_service.create_todo(session, payload)
            return json.dumps(todo.model_dump(mode="json"))

        if name == "update_todo":
            try:
                todo_id = UUID(tool_input["todo_id"])
            except (ValueError, KeyError) as e:
                return f"Invalid todo_id: {e!s}"
            changes: dict[str, Any] = {}
            if "title" in tool_input and tool_input["title"] is not None:
                changes["title"] = tool_input["title"]
            if "description" in tool_input and tool_input["description"] is not None:
                changes["description"] = tool_input["description"]
            if "is_completed" in tool_input and tool_input["is_completed"] is not None:
                is_completed = tool_input["is_completed"]
                if not isinstance(is_completed, bool):
                    type_name = type(is_completed).__name__
                    return f"Invalid is_completed value: expected boolean, got {type_name}"
                changes["is_completed"] = is_completed
            todo = await todo_service.update_todo(session, todo_id, TodoUpdate(**changes))
            if todo is None:
                return f"Todo {tool_input['todo_id']} not found"
            return json.dumps(todo.model_dump(mode="json"))

        if name == "delete_todo":
            try:
                deleted = await todo_service.delete_todo(session, UUID(tool_input["todo_id"]))
            except (ValueError, KeyError) as e:
                return f"Invalid todo_id: {e!s}"
            if deleted:
                return f"Deleted todo {tool_input['todo_id']}"
            return f"Todo {tool_input['todo_id']} not found"

        if name == "clear_completed":
            completed_todos = await todo_service.list_todos(session, completed=True)
            count = 0
            for t in completed_todos:
                if await todo_service.delete_todo(session, t.id):
                    count += 1
            return f"Cleared {count} completed todo{'s' if count != 1 else ''}"

    return f"Unknown tool: {name}"


async def _agentic_loop(
    messages: list[Any],
    on_event: Any | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Run the LLM agentic loop, optionally calling ``on_event`` for each step.

    ``on_event`` (if provided) is awaited with a dict for tool events so the
    streaming endpoint can relay them to the client. The return value is
    ``(final_text, intermediate_turns)`` where ``intermediate_turns`` is a
    list of dicts shaped like the OpenAI chat-completions messages
    (assistant tool_calls + tool results) for later persistence.
    """
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": _SYSTEM})

    call_kwargs: dict[str, Any] = {
        "model": settings.chat_model,
        "messages": messages,
        "tools": _TOOLS,
        "max_tokens": 4096,
    }
    if settings.chat_api_base:
        call_kwargs["api_base"] = settings.chat_api_base
    if _is_ollama_cloud() and settings.ollama_api_key:
        call_kwargs["api_key"] = settings.ollama_api_key

    max_iterations = 10
    iteration = 0
    final_text = ""
    intermediate: list[dict[str, Any]] = []

    while iteration < max_iterations:
        iteration += 1
        logger.debug(f"Chat iteration {iteration}/{max_iterations}")
        try:
            response = await litellm.acompletion(**call_kwargs)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return (f"Error communicating with the model: {str(e)[:100]}", intermediate)

        choice = response.choices[0]
        finish_reason: str = choice.finish_reason or "stop"
        msg = choice.message

        logger.debug(
            f"LLM response: finish_reason={finish_reason}, "
            f"tool_calls={msg.tool_calls}, content={msg.content}"
        )

        if finish_reason not in ("tool_calls", "function_call"):
            response_text = str(msg.content or "").strip()

            # Ollama workaround: parse JSON tool calls from text (e.g., inside ```json blocks)
            if response_text and not msg.tool_calls:
                parsed_calls = _try_parse_ollama_tool_calls(response_text)
                if parsed_calls:
                    msg.tool_calls = [
                        type('ToolCall', (), {
                            'id': f'ollama_tool_call_{i}',
                            'function': type('Function', (), {
                                'name': tc["name"],
                                'arguments': json.dumps(tc["arguments"])
                            })()
                        })()
                        for i, tc in enumerate(parsed_calls)
                    ]
                    msg.content = ""  # strip preamble text
                    finish_reason = "tool_calls"

            if finish_reason not in ("tool_calls", "function_call"):
                if not response_text:
                    logger.warning(
                        f"Empty response from model. Finish reason: {finish_reason}, "
                        f"Tool calls: {msg.tool_calls}"
                    )
                final_text = response_text
                return (final_text, intermediate)

        tool_calls = msg.tool_calls or []
        if not tool_calls:
            return (str(msg.content or ""), intermediate)

        # Record the assistant turn (with tool_calls) and then each tool result
        assistant_payload: dict[str, Any] = {
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ],
        }
        messages.append(assistant_payload)
        intermediate.append(assistant_payload)

        for tc in tool_calls:
            tool_args = json.loads(tc.function.arguments)
            result = await _run_tool(tc.function.name, tool_args)
            logger.debug(f"Tool execution: {tc.function.name}({tool_args}) -> {result}")
            tool_msg = {"role": "tool", "tool_call_id": tc.id, "content": result}
            messages.append(tool_msg)
            intermediate.append(tool_msg)
            if on_event is not None:
                await on_event(
                    {
                        "name": tc.function.name,
                        "arguments": tool_args,
                        "result": result,
                    }
                )

        if iteration >= max_iterations - 1:
            final_text = "\n".join(
                f"✓ {tc.function.name}: {json.loads(tc.function.arguments)}"
                for tc in tool_calls
            ) or "Task completed."
            return (final_text, intermediate)

    return (
        "Chat exceeded maximum iterations. The model may not support tool use well.",
        intermediate,
    )


async def chat(message: str, history: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Run a chat turn. Returns ``(final_text, intermediate_turns_for_persistence)``."""
    _setup_env()
    messages: list[Any] = list(history)
    messages.append({"role": "user", "content": message})
    return await _agentic_loop(messages)


async def chat_stream(
    message: str, history: list[dict[str, Any]]
) -> Any:
    """Async generator yielding SSE-style event dicts:
      - {"type": "token", "delta": str}     — text delta from the model
      - {"type": "tool",  "name", "arguments", "result", "persist": [...]} — tool call
      - {"type": "done",  "response": str}   — final reply
      - {"type": "error", "message": str}    — any failure
    """
    _setup_env()
    messages: list[Any] = list(history)
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": _SYSTEM})
    messages.append({"role": "user", "content": message})

    call_kwargs: dict[str, Any] = {
        "model": settings.chat_model,
        "messages": messages,
        "tools": _TOOLS,
        "max_tokens": 4096,
        "stream": True,
    }
    if settings.chat_api_base:
        call_kwargs["api_base"] = settings.chat_api_base
    if _is_ollama_cloud() and settings.ollama_api_key:
        call_kwargs["api_key"] = settings.ollama_api_key

    max_iterations = 10
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        try:
            response = await litellm.acompletion(**call_kwargs)
        except Exception as exc:
            yield {"type": "error", "message": str(exc)[:200]}
            return

        # Consume the streamed chunks, accumulating text + tool calls
        content_parts: list[str] = []
        tool_calls_acc: dict[int, dict[str, Any]] = {}
        try:
            async for chunk in response:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                # Text delta
                if getattr(delta, "content", None):
                    text_piece = str(delta.content)
                    content_parts.append(text_piece)
                    # Suppress visible token if the text is a JSON tool call
                    # emitted by Ollama (which lacks native streaming tool_calls).
                    if not _try_parse_ollama_tool_calls(text_piece):
                        yield {"type": "token", "delta": text_piece}
                # Tool call deltas: aggregate by index
                tc_deltas = getattr(delta, "tool_calls", None)
                if tc_deltas:
                    for tc in tc_deltas:
                        idx = getattr(tc, "index", 0) or 0
                        slot = tool_calls_acc.setdefault(
                            idx,
                            {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            },
                        )
                        if getattr(tc, "id", None):
                            slot["id"] = tc.id
                        fn = getattr(tc, "function", None)
                        if fn is not None:
                            if getattr(fn, "name", None):
                                slot["function"]["name"] = (
                                    slot["function"].get("name", "") + fn.name
                                )
                            if getattr(fn, "arguments", None):
                                slot["function"]["arguments"] = (
                                    slot["function"].get("arguments", "")
                                    + fn.arguments
                                )
        except Exception as exc:
            yield {"type": "error", "message": f"Stream error: {exc}"}
            return

        full_text = "".join(content_parts).strip()
        ordered_tool_calls = [tool_calls_acc[i] for i in sorted(tool_calls_acc)]
        intermediate: list[dict[str, Any]] = []

        # Ollama streaming workaround: when no native tool_calls were received,
        # the model may have emitted tool calls as plain JSON text.
        if not ordered_tool_calls and full_text:
            parsed_calls = _try_parse_ollama_tool_calls(full_text)
            if parsed_calls:
                ordered_tool_calls = [
                    {
                        "id": f"ollama_tool_call_{i}",
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    }
                    for i, tc in enumerate(parsed_calls)
                ]
                full_text = ""

        if ordered_tool_calls:
            # Some shims split the name; try to take it from arguments (Ollama)
            for tc in ordered_tool_calls:
                if not tc["function"].get("name"):
                    args_str = tc["function"].get("arguments", "")
                    try:
                        parsed_args = json.loads(args_str) if args_str else {}
                    except json.JSONDecodeError:
                        parsed_args = {}
                    if "name" in parsed_args:
                        tc["function"]["name"] = str(parsed_args.pop("name"))
                        tc["function"]["arguments"] = json.dumps(parsed_args)
            # If still no name, try the Ollama JSON-in-text fallback
            if not ordered_tool_calls[0]["function"].get("name") and full_text:
                parsed_calls = _try_parse_ollama_tool_calls(full_text)
                if parsed_calls:
                    # Fill in names on existing entries or append new ones
                    parsed_idx = 0
                    for tc in ordered_tool_calls:
                        if not tc["function"].get("name") and parsed_idx < len(parsed_calls):
                            tc["function"]["name"] = parsed_calls[parsed_idx]["name"]
                            args = tc["function"].get("arguments", "")
                            if not args or args == "{}":
                                tc["function"]["arguments"] = json.dumps(
                                    parsed_calls[parsed_idx]["arguments"]
                                )
                            parsed_idx += 1
                    # If there are more parsed calls than existing entries, append them
                    while parsed_idx < len(parsed_calls):
                        pc = parsed_calls[parsed_idx]
                        ordered_tool_calls.append({
                            "id": f"ollama_tool_call_{parsed_idx}",
                            "type": "function",
                            "function": {
                                "name": pc["name"],
                                "arguments": json.dumps(pc["arguments"]),
                            },
                        })
                        parsed_idx += 1
                    full_text = ""

            if ordered_tool_calls[0]["function"].get("name"):
                assistant_payload = {
                    "role": "assistant",
                    "content": full_text,
                    "tool_calls": ordered_tool_calls,
                }
                messages.append(assistant_payload)
                intermediate.append(assistant_payload)

                for tc in ordered_tool_calls:
                    try:
                        tool_args = json.loads(tc["function"]["arguments"] or "{}")
                    except json.JSONDecodeError:
                        tool_args = {}
                    result = await _run_tool(tc["function"]["name"], tool_args)
                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    }
                    messages.append(tool_msg)
                    intermediate.append(tool_msg)
                    yield {
                        "type": "tool",
                        "name": tc["function"]["name"],
                        "arguments": tool_args,
                        "result": result,
                        "persist": [assistant_payload, tool_msg],
                    }

                if iteration >= max_iterations - 1:
                    summary = "\n".join(
                        f"✓ {tc['function']['name']}"
                        for tc in ordered_tool_calls
                    ) or "Task completed."
                    yield {"type": "done", "response": summary, "intermediate": intermediate}
                    return
                continue  # next iteration with appended tool results

        # No tool calls → done
        yield {"type": "done", "response": full_text, "intermediate": intermediate}
        return

    yield {
        "type": "done",
        "response": "Chat exceeded maximum iterations.",
        "intermediate": [],
    }
