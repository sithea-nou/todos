"""MCP server exposing todo operations to LLM clients.

The tools here are thin wrappers around `app.services.todo_service`. They open
their own AsyncSession via the shared `async_session_factory` so they do not
depend on a request-scoped FastAPI dependency.

The instance is mounted in `app/main.py` at `/mcp` over Streamable HTTP.
"""

from uuid import UUID

from fastmcp import FastMCP

from app.database import async_session_factory
from app.models.todo import TodoCreate, TodoRead, TodoUpdate
from app.services import todo_service

mcp = FastMCP("mytodo")


def _serialize(todo: TodoRead) -> dict:
    """Serialize a TodoRead to a JSON-friendly dict (datetimes → ISO strings)."""
    return todo.model_dump(mode="json")


async def _session_do(coro):
    """Run a service coroutine inside its own AsyncSession and return its result.

    Centralizing session management here means each tool only declares the
    service-level work it actually wants to do.
    """
    async with async_session_factory() as session:
        return await coro(session)


@mcp.tool
async def list_todos(completed: bool | None = None) -> list[dict]:
    """List all todos. Optionally filter by completion status.

    Args:
        completed: True to return only completed todos, False for only active,
            None (default) for all.
    """
    todos = await _session_do(lambda s: todo_service.list_todos(s, completed=completed))
    return [_serialize(t) for t in todos]


@mcp.tool
async def get_todo(todo_id: str) -> dict:
    """Fetch a single todo by its UUID.

    Args:
        todo_id: The UUID of the todo (as a string).
    """
    try:
        parsed = UUID(todo_id)
    except ValueError as exc:
        raise ValueError(f"Invalid todo id: {todo_id!r}") from exc

    todo = await _session_do(lambda s: todo_service.get_todo(s, parsed))
    if todo is None:
        raise ValueError(f"Todo {todo_id} not found")
    return _serialize(todo)


@mcp.tool
async def create_todo(title: str, description: str | None = None) -> dict:
    """Create a new todo.

    Args:
        title: Short title for the todo (1-200 chars).
        description: Optional longer description (max 2000 chars).
    """
    payload = TodoCreate(title=title, description=description)
    todo = await _session_do(lambda s: todo_service.create_todo(s, payload))
    return _serialize(todo)


@mcp.tool
async def update_todo(
    todo_id: str,
    title: str | None = None,
    description: str | None = None,
    is_completed: bool | None = None,
) -> dict:
    """Update an existing todo. Only the fields you provide are changed.

    Args:
        todo_id: The UUID of the todo.
        title: New title (omit to leave unchanged).
        description: New description (omit to leave unchanged).
        is_completed: New completion flag (omit to leave unchanged).
    """
    try:
        parsed = UUID(todo_id)
    except ValueError as exc:
        raise ValueError(f"Invalid todo id: {todo_id!r}") from exc

    # Only include fields the caller explicitly provided; passing None explicitly
    # marks them as "set" in Pydantic v2, which would overwrite existing values.
    changes: dict = {
        k: v
        for k, v in {
            "title": title, "description": description, "is_completed": is_completed
        }.items()
        if v is not None
    }
    payload = TodoUpdate(**changes)
    todo = await _session_do(lambda s: todo_service.update_todo(s, parsed, payload))
    if todo is None:
        raise ValueError(f"Todo {todo_id} not found")
    return _serialize(todo)


@mcp.tool
async def delete_todo(todo_id: str) -> str:
    """Delete a todo by its UUID.

    Args:
        todo_id: The UUID of the todo.
    """
    try:
        parsed = UUID(todo_id)
    except ValueError as exc:
        raise ValueError(f"Invalid todo id: {todo_id!r}") from exc

    deleted = await _session_do(lambda s: todo_service.delete_todo(s, parsed))
    if not deleted:
        raise ValueError(f"Todo {todo_id} not found")
    return f"Deleted todo {todo_id}"


@mcp.tool
async def clear_completed() -> str:
    """Delete every todo that is currently marked as completed.

    Returns a summary of how many were removed.
    """
    completed = await _session_do(lambda s: todo_service.list_todos(s, completed=True))
    count = 0
    async with async_session_factory() as session:
        for todo in completed:
            ok = await todo_service.delete_todo(session, todo.id)
            if ok:
                count += 1
    return f"Cleared {count} completed todo{'s' if count != 1 else ''}"
