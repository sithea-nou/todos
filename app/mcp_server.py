"""MCP server exposing todo operations to LLM clients.

The tools here are thin wrappers around `app.services.todo_service`. They open
their own AsyncSession via the shared `async_session_factory` so they do not
depend on a request-scoped FastAPI dependency.

The instance is mounted in `app/main.py` at `/mcp` over Streamable HTTP.
"""

from collections.abc import Awaitable, Callable
from datetime import date as date_type
from typing import Any
from uuid import UUID

from fastmcp import FastMCP
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.todo import TodoCreate, TodoRead, TodoUpdate
from app.services import todo_service

mcp = FastMCP("mytodo")


def _serialize(todo: TodoRead) -> dict[str, Any]:
    """Serialize a TodoRead to a JSON-friendly dict (datetimes → ISO strings)."""
    return todo.model_dump(mode="json")


async def _session_do[T](coro: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Run a service coroutine inside its own AsyncSession and return its result."""
    async with async_session_factory() as session:
        return await coro(session)


def _parse_uuid(todo_id: str) -> UUID:
    """Parse and validate a UUID string, raising ValueError with context."""
    try:
        return UUID(todo_id)
    except ValueError as exc:
        raise ValueError(f"Invalid todo id: {todo_id!r}") from exc


@mcp.tool
async def list_todos(
    completed: bool | None = None,
    order_by: str = "position",
    q: str | None = None,
    priority: int | None = None,
    tag: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict[str, Any]]:
    """List todos. Optionally filter, search, paginate, and sort.

    Args:
        completed: True to return only completed todos, False for only active,
            None (default) for all.
        order_by: Sort order — "position" (default), "priority", or "due_date".
        q: Optional substring search over title and description (case-insensitive).
        priority: Filter by exact priority value (0=none, 1=low, 2=med, 3=high).
        tag: Filter by a tag token (tags are stored comma-separated).
        limit: Optional max number of todos to return (1-500).
        offset: Optional number of todos to skip (>= 0).
    """
    todos = await _session_do(
        lambda s: todo_service.list_todos(
            s,
            completed=completed,
            order_by=order_by,
            q=q,
            priority=priority,
            tag=tag,
            limit=limit,
            offset=offset,
        )
    )
    return [_serialize(t) for t in todos]


@mcp.tool
async def get_todo(todo_id: str) -> dict[str, Any]:
    """Fetch a single (active) todo by its UUID.

    Args:
        todo_id: The UUID of the todo (as a string).
    """
    parsed = _parse_uuid(todo_id)
    todo = await _session_do(lambda s: todo_service.get_todo(s, parsed))
    if todo is None:
        raise ValueError(f"Todo {todo_id} not found")
    return _serialize(todo)


@mcp.tool
async def create_todo(
    title: str,
    description: str | None = None,
    priority: int | None = None,
    due_date: str | None = None,
    tags: str | None = None,
) -> dict[str, Any]:
    """Create a new todo.

    Args:
        title: Short title for the todo (1-200 chars).
        description: Optional longer description (max 2000 chars).
        priority: Optional priority. 0=none, 1=low(P3), 2=med(P2), 3+=high(P1).
            Only set this if the user explicitly mentions priority.
        due_date: Optional due date in YYYY-MM-DD format.
            Only set this if the user mentions a deadline.
        tags: Optional comma-separated tags, e.g. "work,urgent".
            Only set this if the user mentions tags or categories.
    """
    parsed_date = None
    if due_date is not None:
        parsed_date = date_type.fromisoformat(due_date)

    payload = TodoCreate(
        title=title,
        description=description,
        priority=priority if priority is not None else 0,
        due_date=parsed_date,
        tags=tags,
    )
    todo = await _session_do(lambda s: todo_service.create_todo(s, payload))
    return _serialize(todo)


@mcp.tool
async def update_todo(
    todo_id: str,
    title: str | None = None,
    description: str | None = None,
    is_completed: bool | None = None,
    priority: int | None = None,
    due_date: str | None = None,
    tags: str | None = None,
) -> dict[str, Any]:
    """Update an existing todo. Only the fields you provide are changed.

    Args:
        todo_id: The UUID of the todo.
        title: New title (omit to leave unchanged).
        description: New description (omit to leave unchanged).
        is_completed: New completion flag (omit to leave unchanged).
        priority: New priority. 0=none, 1=low(P3), 2=med(P2), 3+=high(P1).
            Only set if the user explicitly asks to change priority.
        due_date: New due date in YYYY-MM-DD format, or "clear" to
            remove it. Only set if the user mentions a deadline.
        tags: New comma-separated tags, e.g. "work,urgent". Use "clear" to
            remove all tags. Only set if the user mentions tags.
    """
    parsed = _parse_uuid(todo_id)

    changes: dict[str, Any] = {}
    if title is not None:
        changes["title"] = title
    if description is not None:
        changes["description"] = description
    if is_completed is not None:
        changes["is_completed"] = is_completed
    if priority is not None:
        changes["priority"] = priority
    if due_date is not None:
        if due_date == "clear":
            changes["due_date"] = None
        else:
            changes["due_date"] = date_type.fromisoformat(due_date)
    if tags is not None:
        changes["tags"] = None if tags == "clear" else tags

    payload = TodoUpdate(**changes)
    todo = await _session_do(lambda s: todo_service.update_todo(s, parsed, payload))
    if todo is None:
        raise ValueError(f"Todo {todo_id} not found")
    return _serialize(todo)


@mcp.tool
async def delete_todo(todo_id: str) -> str:
    """Move a todo to the trash (soft-delete). It can be restored later.

    Args:
        todo_id: The UUID of the todo.
    """
    parsed = _parse_uuid(todo_id)
    deleted = await _session_do(lambda s: todo_service.delete_todo(s, parsed))
    if not deleted:
        raise ValueError(f"Todo {todo_id} not found")
    return f"Deleted todo {todo_id}"


@mcp.tool
async def restore_todo(todo_id: str) -> dict[str, Any]:
    """Restore a previously soft-deleted todo from the trash.

    Args:
        todo_id: The UUID of the todo to restore.
    """
    parsed = _parse_uuid(todo_id)
    todo = await _session_do(lambda s: todo_service.restore_todo(s, parsed))
    if todo is None:
        raise ValueError(f"Todo {todo_id} not found in trash")
    return _serialize(todo)


@mcp.tool
async def clear_completed() -> str:
    """Soft-delete every todo that is currently marked as completed.

    Returns a summary of how many were moved to the trash.
    """
    completed = await _session_do(
        lambda s: todo_service.list_todos(s, completed=True)
    )
    count = 0
    async with async_session_factory() as session:
        for todo in completed:
            ok = await todo_service.delete_todo(session, todo.id)
            if ok:
                count += 1
    return f"Cleared {count} completed todo{'s' if count != 1 else ''}"


@mcp.tool
async def reorder_todos(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Batch-reorder todos by updating their positions.

    Args:
        items: A list of objects with "id" (UUID string) and "position" (int).
            Example: [{"id": "abc-123", "position": 0}, {"id": "def-456", "position": 1}]
    """
    parsed: list[tuple[UUID, int]] = []
    for item in items:
        parsed.append((UUID(item["id"]), int(item["position"])))
    todos = await _session_do(lambda s: todo_service.reorder_todos(s, parsed))
    return [_serialize(t) for t in todos]


@mcp.tool
async def get_todo_stats() -> dict[str, Any]:
    """Return aggregate stats over the active todo set:

    - total, active, completed, overdue counts
    - by_priority: {priority_value: count}
    Useful for summarising the user's workload at a glance.
    """
    stats = await _session_do(lambda s: todo_service.get_stats(s))
    return stats.model_dump(mode="json")
