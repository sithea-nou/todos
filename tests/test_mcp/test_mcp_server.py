"""Tests for the MCP server tools exposed to LLM clients."""

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from sqlmodel import select

from app.database import AsyncSession
from app.models.todo import Todo


async def test_create_then_list_roundtrip(
    mcp_client: Client, session: AsyncSession
) -> None:
    """A todo created via the MCP tool is visible via list_todos and the DB."""
    created = await mcp_client.call_tool(
        "create_todo", {"title": "MCP test", "description": "hi"}
    )
    assert created.data["title"] == "MCP test"
    assert created.data["description"] == "hi"
    assert created.data["is_completed"] is False
    assert created.data["priority"] == 0
    todo_id = created.data["id"]

    rows = (await session.execute(select(Todo))).scalars().all()
    assert len(rows) == 1
    assert str(rows[0].id) == todo_id

    listed = await mcp_client.call_tool("list_todos", {})
    assert len(listed.data) == 1
    assert listed.data[0]["id"] == todo_id


async def test_create_todo_with_priority_and_due_date(
    mcp_client: Client,
) -> None:
    created = await mcp_client.call_tool(
        "create_todo", {"title": "Important", "priority": 3, "due_date": "2026-07-15"}
    )
    assert created.data["priority"] == 3
    assert created.data["due_date"] == "2026-07-15"


async def test_list_todos_filter_completed(mcp_client: Client) -> None:
    """The completed filter narrows results to the requested state."""
    a = await mcp_client.call_tool("create_todo", {"title": "A"})
    b = await mcp_client.call_tool("create_todo", {"title": "B"})
    await mcp_client.call_tool(
        "update_todo", {"todo_id": b.data["id"], "is_completed": True}
    )

    all_todos = await mcp_client.call_tool("list_todos", {})
    assert len(all_todos.data) == 2

    only_completed = await mcp_client.call_tool("list_todos", {"completed": True})
    assert len(only_completed.data) == 1
    assert only_completed.data[0]["id"] == b.data["id"]

    only_active = await mcp_client.call_tool("list_todos", {"completed": False})
    assert len(only_active.data) == 1
    assert only_active.data[0]["id"] == a.data["id"]


async def test_list_todos_order_by(mcp_client: Client) -> None:
    await mcp_client.call_tool("create_todo", {"title": "Low", "priority": 1})
    await mcp_client.call_tool("create_todo", {"title": "High", "priority": 3})

    by_priority = await mcp_client.call_tool("list_todos", {"order_by": "priority"})
    assert len(by_priority.data) == 2
    assert by_priority.data[0]["priority"] >= by_priority.data[1]["priority"]


async def test_get_todo(mcp_client: Client) -> None:
    """get_todo returns the same todo by UUID."""
    created = await mcp_client.call_tool("create_todo", {"title": "Get me"})
    todo_id = created.data["id"]

    fetched = await mcp_client.call_tool("get_todo", {"todo_id": todo_id})
    assert fetched.data["id"] == todo_id
    assert fetched.data["title"] == "Get me"


async def test_get_todo_invalid_uuid_raises(mcp_client: Client) -> None:
    """Non-UUID strings are rejected before hitting the database."""
    with pytest.raises(ToolError, match="Invalid todo id"):
        await mcp_client.call_tool("get_todo", {"todo_id": "not-a-uuid"})


async def test_get_todo_not_found_raises(mcp_client: Client) -> None:
    """A well-formed but unknown UUID raises a not-found error."""
    missing = "00000000-0000-0000-0000-000000000000"
    with pytest.raises(ToolError, match="not found"):
        await mcp_client.call_tool("get_todo", {"todo_id": missing})


async def test_update_todo_partial(mcp_client: Client) -> None:
    """Only the fields provided in the call are changed."""
    created = await mcp_client.call_tool(
        "create_todo", {"title": "old", "description": "keep me"}
    )
    todo_id = created.data["id"]

    updated = await mcp_client.call_tool(
        "update_todo", {"todo_id": todo_id, "is_completed": True}
    )
    assert updated.data["title"] == "old"
    assert updated.data["description"] == "keep me"
    assert updated.data["is_completed"] is True


async def test_update_todo_priority_and_due_date(mcp_client: Client) -> None:
    created = await mcp_client.call_tool("create_todo", {"title": "Task"})
    todo_id = created.data["id"]

    updated = await mcp_client.call_tool(
        "update_todo", {"todo_id": todo_id, "priority": 2, "due_date": "2026-08-01"}
    )
    assert updated.data["priority"] == 2
    assert updated.data["due_date"] == "2026-08-01"


async def test_update_todo_clear_due_date(mcp_client: Client) -> None:
    created = await mcp_client.call_tool(
        "create_todo", {"title": "Task", "due_date": "2026-08-01"}
    )
    todo_id = created.data["id"]

    updated = await mcp_client.call_tool(
        "update_todo", {"todo_id": todo_id, "due_date": "clear"}
    )
    assert updated.data["due_date"] is None


async def test_delete_todo(mcp_client: Client) -> None:
    """delete_todo removes the row and reports the deleted id."""
    created = await mcp_client.call_tool("create_todo", {"title": "bye"})
    todo_id = created.data["id"]

    result = await mcp_client.call_tool("delete_todo", {"todo_id": todo_id})
    assert result.data == f"Deleted todo {todo_id}"

    with pytest.raises(ToolError, match="not found"):
        await mcp_client.call_tool("get_todo", {"todo_id": todo_id})


async def test_clear_completed(mcp_client: Client) -> None:
    """clear_completed removes only completed todos and reports the count."""
    active = await mcp_client.call_tool("create_todo", {"title": "active"})
    done1 = await mcp_client.call_tool("create_todo", {"title": "done"})
    done2 = await mcp_client.call_tool("create_todo", {"title": "done 2"})
    for tid in (done1.data["id"], done2.data["id"]):
        await mcp_client.call_tool(
            "update_todo", {"todo_id": tid, "is_completed": True}
        )

    result = await mcp_client.call_tool("clear_completed", {})
    assert result.data == "Cleared 2 completed todos"

    remaining = await mcp_client.call_tool("list_todos", {})
    assert len(remaining.data) == 1
    assert remaining.data[0]["id"] == active.data["id"]


async def test_reorder_todos(mcp_client: Client) -> None:
    t1 = await mcp_client.call_tool("create_todo", {"title": "A"})
    t2 = await mcp_client.call_tool("create_todo", {"title": "B"})
    id1 = t1.data["id"]
    id2 = t2.data["id"]

    result = await mcp_client.call_tool(
        "reorder_todos",
        {"items": [{"id": id2, "position": 0}, {"id": id1, "position": 1}]},
    )
    assert len(result.data) >= 2
