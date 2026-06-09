"""Chat service: LLM agent with todo tool use.

Supports any provider via LiteLLM:
  - Anthropic  → CHAT_MODEL=claude-sonnet-4-6    + ANTHROPIC_API_KEY
  - OpenAI     → CHAT_MODEL=gpt-4o               + OPENAI_API_KEY
  - Ollama     → CHAT_MODEL=ollama/llama3.1       (CHAT_API_BASE defaults to localhost)
  - Any OpenAI-compatible server:
                 CHAT_MODEL=openai/my-model        + CHAT_API_BASE=http://host:port/v1
  - Ollama     → CHAT_MODEL=ollama/llama3.1       (CHAT_API_BASE defaults to localhost)
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

_SYSTEM = (
    "You are a helpful todo assistant. Use the available tools to manage the user's todos. "
    "Be concise and friendly."
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
    """Export config API keys to env vars so LiteLLM can find them."""
    if settings.anthropic_api_key:
        os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
    if settings.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)



async def _run_tool(name: str, tool_input: dict[str, Any]) -> str:
    """Execute a todo tool and return a JSON string result."""
    async with async_session_factory() as session:
        if name == "list_todos":
            completed = tool_input.get("completed")
            if completed is not None and not isinstance(completed, bool):
                return f"Invalid completed value: expected boolean or null, got {type(completed).__name__}"
            todos = await todo_service.list_todos(session, completed=completed)
            return json.dumps([t.model_dump(mode="json") for t in todos])

        if name == "get_todo":
            try:
                todo = await todo_service.get_todo(session, UUID(tool_input["todo_id"]))
            except (ValueError, KeyError) as e:
                return f"Invalid todo_id: {str(e)}"
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
                return f"Invalid todo_id: {str(e)}"
            changes: dict[str, Any] = {}
            if "title" in tool_input and tool_input["title"] is not None:
                changes["title"] = tool_input["title"]
            if "description" in tool_input and tool_input["description"] is not None:
                changes["description"] = tool_input["description"]
            if "is_completed" in tool_input and tool_input["is_completed"] is not None:
                is_completed = tool_input["is_completed"]
                if not isinstance(is_completed, bool):
                    return f"Invalid is_completed value: expected boolean, got {type(is_completed).__name__}"
                changes["is_completed"] = is_completed
            todo = await todo_service.update_todo(session, todo_id, TodoUpdate(**changes))
            if todo is None:
                return f"Todo {tool_input['todo_id']} not found"
            return json.dumps(todo.model_dump(mode="json"))

        if name == "delete_todo":
            try:
                deleted = await todo_service.delete_todo(session, UUID(tool_input["todo_id"]))
            except (ValueError, KeyError) as e:
                return f"Invalid todo_id: {str(e)}"
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


async def chat(message: str, history: list[dict[str, Any]]) -> str:
    """Run a chat turn through the LLM agentic loop."""
    _setup_env()

    messages: list[Any] = list(history)
    messages.append({"role": "user", "content": message})

    call_kwargs: dict[str, Any] = {
        "model": settings.chat_model,
        "messages": messages,
        "tools": _TOOLS,
        "max_tokens": 4096,
    }
    if settings.chat_api_base:
        call_kwargs["api_base"] = settings.chat_api_base

    max_iterations = 10
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        logger.debug(f"Chat iteration {iteration}/{max_iterations}")
        try:
            response = await litellm.acompletion(**call_kwargs)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return f"Error communicating with the model: {str(e)[:100]}"

        choice = response.choices[0]
        finish_reason: str = choice.finish_reason or "stop"
        msg = choice.message

        logger.debug(f"LLM response: finish_reason={finish_reason}, tool_calls={msg.tool_calls}, content={msg.content}")
        logger.debug(f"Full response object: {response}")

        if finish_reason not in ("tool_calls", "function_call"):
            response_text = str(msg.content or "").strip()

            # Ollama workaround: parse JSON tool calls from text (e.g., inside ```json blocks)
            if response_text and not msg.tool_calls:
                try:
                    # Try to extract JSON from markdown code block or plain JSON
                    json_str = response_text
                    if "```json" in json_str:
                        json_str = json_str.split("```json")[1].split("```")[0].strip()
                    elif "```" in json_str:
                        json_str = json_str.split("```")[1].split("```")[0].strip()

                    parsed = json.loads(json_str)
                    if isinstance(parsed, dict) and "name" in parsed and "arguments" in parsed:
                        # Convert to tool call format
                        tool_call = type('ToolCall', (), {
                            'id': 'ollama_tool_call',
                            'function': type('Function', (), {
                                'name': parsed["name"],
                                'arguments': json.dumps(parsed["arguments"])
                            })()
                        })()
                        msg.tool_calls = [tool_call]
                        # Continue to process this as a tool call
                        finish_reason = "tool_calls"
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass  # Not a tool call, proceed normally

            if finish_reason not in ("tool_calls", "function_call"):
                if not response_text:
                    logger.warning(f"Empty response from model. Finish reason: {finish_reason}, Tool calls: {msg.tool_calls}")
                return response_text

        tool_calls = msg.tool_calls or []
        if not tool_calls:
            return str(msg.content or "")

        # Execute tools and collect results
        tool_results = []
        messages.append(
            {
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
        )

        for tc in tool_calls:
            tool_args: dict[str, Any] = json.loads(tc.function.arguments)
            result = await _run_tool(tc.function.name, tool_args)
            logger.debug(f"Tool execution: {tc.function.name}({tool_args}) -> {result}")
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            tool_results.append(f"✓ {tc.function.name}: {result[:100]}")

        # If this is the last iteration or model keeps returning tools, return confirmation
        if iteration >= max_iterations - 1:
            return "\n".join(tool_results) if tool_results else "Task completed."

    return "Chat exceeded maximum iterations. The model may not support tool use well."
