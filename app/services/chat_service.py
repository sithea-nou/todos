"""Chat service: LLM agent with todo tool use.

Supports any provider via LiteLLM:
  - Anthropic  → CHAT_MODEL=claude-sonnet-4-6    + ANTHROPIC_API_KEY
  - OpenAI     → CHAT_MODEL=gpt-4o               + OPENAI_API_KEY
  - Ollama     → CHAT_MODEL=ollama/llama3.1       (CHAT_API_BASE defaults to localhost)
  - Any OpenAI-compatible server:
                 CHAT_MODEL=openai/my-model        + CHAT_API_BASE=http://host:port/v1

Tool definitions and execution are routed through the MCP server (``app.mcp_server``),
which is the single source of truth. The OpenAI-format tool schemas used by the LLM
are derived from the MCP server's registered tools at call time.
"""

import json
import logging
import os
from typing import Any

import litellm
from fastmcp import Client
from fastmcp.exceptions import ToolError

from app.config import settings
from app.mcp_server import mcp

logger = logging.getLogger(__name__)
os.environ.setdefault("LITELLM_LOG", "DEBUG")

# ---------------------------------------------------------------------------
# MCP → OpenAI tool schema conversion
# ---------------------------------------------------------------------------

_cached_openai_tools: list[dict[str, Any]] | None = None


def _flatten_anyof(schema: dict[str, Any]) -> dict[str, Any]:
    """Convert ``anyOf[X, null]`` patterns to a simple type.

    OpenAI function calling doesn't support ``anyOf``. Optional fields
    expressed as ``anyOf`` with a null alternative are flattened to the
    non-null type; optionality is conveyed by omitting the field from
    ``required``.
    """
    if "anyOf" not in schema:
        return schema
    non_null = [s for s in schema["anyOf"] if s.get("type") != "null"]
    if len(non_null) == 1:
        result = {**non_null[0]}
        if "description" in schema:
            result["description"] = schema["description"]
        if "default" in schema:
            result["default"] = schema["default"]
        return result
    # Fallback: keep anyOf as-is (unusual for our tools)
    return schema


def _mcp_schema_to_openai(input_schema: dict[str, Any]) -> dict[str, Any]:
    """Convert an MCP tool ``inputSchema`` to OpenAI function-calling format.

    - Strips ``additionalProperties: false`` (not used by OpenAI).
    - Flattens ``anyOf[X, null]`` → ``type: X`` for optional params.
    - Preserves ``required`` list (fields not in it are optional).
    - Flattens ``items: {additionalProperties: true, type: object}``
      → ``items: {type: object}``.
    """
    props = input_schema.get("properties", {})
    converted: dict[str, Any] = {}
    for name, prop in props.items():
        prop = {k: v for k, v in prop.items() if k != "additionalProperties"}
        prop = _flatten_anyof(prop)
        # Recurse into items for array types
        if prop.get("type") == "array" and "items" in prop:
            items = {k: v for k, v in prop["items"].items() if k != "additionalProperties"}
            items = _flatten_anyof(items)
            prop["items"] = items
        converted[name] = prop
    result: dict[str, Any] = {"type": "object", "properties": converted}
    if "required" in input_schema:
        result["required"] = input_schema["required"]
    return result


async def _build_openai_tools() -> list[dict[str, Any]]:
    """Build OpenAI-format tool definitions from the MCP server.

    Caches the result after the first call; tools are static once registered.
    """
    global _cached_openai_tools
    if _cached_openai_tools is not None:
        return _cached_openai_tools

    async with Client(mcp) as client:
        mcp_tools = await client.list_tools()

    openai_tools: list[dict[str, Any]] = []
    for t in mcp_tools:
        openai_tools.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": _mcp_schema_to_openai(t.inputSchema),
                },
            }
        )

    _cached_openai_tools = openai_tools
    return openai_tools


# ---------------------------------------------------------------------------
# Tool execution via MCP
# ---------------------------------------------------------------------------


async def _run_tool_via_mcp(name: str, tool_input: dict[str, Any]) -> str:
    """Execute a tool through the MCP server and return a JSON string result.

    On success, returns ``json.dumps(result.data)``.
    On ``ToolError`` (e.g. todo not found), returns the error message string.
    """
    try:
        async with Client(mcp) as client:
            result = await client.call_tool(name, tool_input)
    except ToolError as exc:
        return str(exc)
    except Exception as exc:
        logger.error(f"MCP call_tool error for {name}: {exc}")
        return f"Error executing {name}: {str(exc)[:200]}"

    data = result.data
    if isinstance(data, list):
        return json.dumps(data)
    if isinstance(data, dict):
        return json.dumps(data)
    return str(data)


# ---------------------------------------------------------------------------
# Ollama JSON tool-call parser (fallback for models without native tool use)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You are a helpful todo assistant. Use the available tools to manage the user's todos. "
    "Be concise and friendly. "
    "You can create, update, and delete todos; set priorities and due dates; reorder items; "
    "and clear completed todos. "
    "IMPORTANT: Only set priority and due_date when the user explicitly asks for them. "
    "Do NOT assign a default priority or due date if the user doesn't mention it. "
    "When you need to call a tool, output ONLY the required JSON with no other text. "
    "After receiving tool results, answer the user directly "
    "without calling additional tools unless necessary."
)


# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Agentic loop (non-streaming)
# ---------------------------------------------------------------------------


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
    tools = await _build_openai_tools()

    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": _SYSTEM})

    call_kwargs: dict[str, Any] = {
        "model": settings.chat_model,
        "messages": messages,
        "tools": tools,
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
            result = await _run_tool_via_mcp(tc.function.name, tool_args)
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


# ---------------------------------------------------------------------------
# Streaming chat
# ---------------------------------------------------------------------------


async def chat(message: str, history: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Run a chat turn. Returns ``(final_text, intermediate_turns_for_persistence)``."""
    _setup_env()
    messages: list[Any] = list(history)
    messages.append({"role": "user", "content": message})
    return await _agentic_loop(messages)


async def chat_stream(
    message: str,
    history: list[dict[str, Any]],
) -> Any:
    """Async generator yielding SSE-style event dicts:
      - {"type": "token", "delta": str}     — text delta from the model
      - {"type": "tool",  "name", "arguments", "result", "persist": [...]} — tool call
      - {"type": "done",  "response": str}   — final reply
      - {"type": "error", "message": str}    — any failure
    """
    _setup_env()
    tools = await _build_openai_tools()
    messages: list[Any] = list(history)
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": _SYSTEM})
    messages.append({"role": "user", "content": message})

    call_kwargs: dict[str, Any] = {
        "model": settings.chat_model,
        "messages": messages,
        "tools": tools,
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
                    result = await _run_tool_via_mcp(tc["function"]["name"], tool_args)
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
