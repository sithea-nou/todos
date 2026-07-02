"""Tests for new MCP server tools: extended list_todos, stats, restore."""

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from app.database import AsyncSession


async def test_list_todos_search(mcp_client: Client) -> None:
    await mcp_client.call_tool("create_todo", {"title": "Buy milk"})
    await mcp_client.call_tool("create_todo", {"title": "Walk dog"})

    results = await mcp_client.call_tool("list_todos", {"q": "milk"})
    assert len(results.data) == 1
    assert results.data[0]["title"] == "Buy milk"


async def test_list_todos_filter_priority(mcp_client: Client) -> None:
    await mcp_client.call_tool("create_todo", {"title": "Low", "priority": 1})
    await mcp_client.call_tool("create_todo", {"title": "High", "priority": 3})

    results = await mcp_client.call_tool("list_todos", {"priority": 3})
    assert len(results.data) == 1
    assert results.data[0]["priority"] == 3


async def test_list_todos_filter_tag(mcp_client: Client) -> None:
    await mcp_client.call_tool(
        "create_todo", {"title": "A", "tags": "work,urgent"}
    )
    await mcp_client.call_tool("create_todo", {"title": "B", "tags": "home"})

    work = await mcp_client.call_tool("list_todos", {"tag": "work"})
    assert len(work.data) == 1
    assert work.data[0]["title"] == "A"


async def test_list_todos_pagination(mcp_client: Client) -> None:
    for i in range(5):
        await mcp_client.call_tool("create_todo", {"title": f"T{i}"})

    page = await mcp_client.call_tool("list_todos", {"limit": 2, "offset": 0})
    assert len(page.data) == 2


async def test_create_todo_with_tags(mcp_client: Client) -> None:
    created = await mcp_client.call_tool(
        "create_todo", {"title": "Tagged", "tags": "a,b"}
    )
    assert created.data["tags"] == "a,b"


async def test_update_todo_tags(mcp_client: Client) -> None:
    created = await mcp_client.call_tool("create_todo", {"title": "X"})
    todo_id = created.data["id"]

    updated = await mcp_client.call_tool(
        "update_todo", {"todo_id": todo_id, "tags": "work,low"}
    )
    assert updated.data["tags"] == "work,low"


async def test_update_todo_clear_tags(mcp_client: Client) -> None:
    created = await mcp_client.call_tool(
        "create_todo", {"title": "X", "tags": "work"}
    )
    todo_id = created.data["id"]

    updated = await mcp_client.call_tool(
        "update_todo", {"todo_id": todo_id, "tags": "clear"}
    )
    assert updated.data["tags"] is None


async def test_get_todo_stats(mcp_client: Client) -> None:
    await mcp_client.call_tool("create_todo", {"title": "active"})
    b = await mcp_client.call_tool("create_todo", {"title": "done"})
    await mcp_client.call_tool(
        "update_todo", {"todo_id": b.data["id"], "is_completed": True}
    )

    stats = await mcp_client.call_tool("get_todo_stats", {})
    assert stats.data["total"] == 2
    assert stats.data["active"] == 1
    assert stats.data["completed"] == 1
    assert isinstance(stats.data["by_priority"], dict)


async def test_delete_then_restore(mcp_client: Client) -> None:
    created = await mcp_client.call_tool("create_todo", {"title": "x"})
    todo_id = created.data["id"]

    await mcp_client.call_tool("delete_todo", {"todo_id": todo_id})

    # Not visible in the active list.
    active = await mcp_client.call_tool("list_todos", {})
    assert all(t["id"] != todo_id for t in active.data)

    # get_todo raises because it's soft-deleted.
    with pytest.raises(ToolError, match="not found"):
        await mcp_client.call_tool("get_todo", {"todo_id": todo_id})

    # Restore it.
    restored = await mcp_client.call_tool("restore_todo", {"todo_id": todo_id})
    assert restored.data["deleted_at"] is None
    assert restored.data["title"] == "x"

    # Visible again.
    active = await mcp_client.call_tool("list_todos", {})
    assert any(t["id"] == todo_id for t in active.data)


async def test_restore_not_in_trash_raises(mcp_client: Client) -> None:
    created = await mcp_client.call_tool("create_todo", {"title": "x"})
    with pytest.raises(ToolError, match="not found in trash"):
        await mcp_client.call_tool(
            "restore_todo", {"todo_id": created.data["id"]}
        )


async def test_clear_completed_now_soft_deletes(
    mcp_client: Client, session: AsyncSession
) -> None:
    """clear_completed moves completed todos to the trash (soft-delete)."""
    active = await mcp_client.call_tool("create_todo", {"title": "active"})
    done = await mcp_client.call_tool("create_todo", {"title": "done"})
    await mcp_client.call_tool(
        "update_todo", {"todo_id": done.data["id"], "is_completed": True}
    )

    result = await mcp_client.call_tool("clear_completed", {})
    assert result.data == "Cleared 1 completed todo"

    remaining = await mcp_client.call_tool("list_todos", {})
    assert len(remaining.data) == 1
    assert remaining.data[0]["id"] == active.data["id"]
