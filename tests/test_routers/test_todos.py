"""Tests for the todos router."""

from uuid import uuid4

from httpx import AsyncClient


async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


async def test_create_todo(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/todos/",
        json={"title": "Test todo", "description": "A test item"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Test todo"
    assert data["description"] == "A test item"
    assert data["is_completed"] is False
    assert data["priority"] == 0
    assert data["due_date"] is None
    assert data["position"] == 0
    assert "id" in data
    assert "created_at" in data


async def test_create_todo_with_priority_and_due_date(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/todos/",
        json={"title": "Priority task", "priority": 3, "due_date": "2026-07-15"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["priority"] == 3
    assert data["due_date"] == "2026-07-15"


async def test_list_todos(client: AsyncClient) -> None:
    await client.post("/api/todos/", json={"title": "First"})
    await client.post("/api/todos/", json={"title": "Second"})

    resp = await client.get("/api/todos/")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


async def test_list_todos_order_by_position(client: AsyncClient) -> None:
    resp = await client.get("/api/todos/?order_by=position")
    assert resp.status_code == 200


async def test_list_todos_order_by_priority(client: AsyncClient) -> None:
    resp = await client.get("/api/todos/?order_by=priority")
    assert resp.status_code == 200


async def test_list_todos_order_by_due_date(client: AsyncClient) -> None:
    resp = await client.get("/api/todos/?order_by=due_date")
    assert resp.status_code == 200


async def test_list_todos_invalid_order_by(client: AsyncClient) -> None:
    resp = await client.get("/api/todos/?order_by=invalid")
    assert resp.status_code == 400


async def test_get_todo(client: AsyncClient) -> None:
    resp = await client.post("/api/todos/", json={"title": "Get me"})
    todo_id = resp.json()["id"]

    resp = await client.get(f"/api/todos/{todo_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Get me"


async def test_get_todo_not_found(client: AsyncClient) -> None:
    fake_id = str(uuid4())
    resp = await client.get(f"/api/todos/{fake_id}")
    assert resp.status_code == 404


async def test_update_todo(client: AsyncClient) -> None:
    resp = await client.post("/api/todos/", json={"title": "Old title"})
    todo_id = resp.json()["id"]

    resp = await client.patch(
        f"/api/todos/{todo_id}",
        json={"title": "New title", "is_completed": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "New title"
    assert data["is_completed"] is True


async def test_update_todo_priority_and_due_date(client: AsyncClient) -> None:
    resp = await client.post("/api/todos/", json={"title": "Task"})
    todo_id = resp.json()["id"]

    resp = await client.patch(
        f"/api/todos/{todo_id}",
        json={"priority": 2, "due_date": "2026-08-01"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["priority"] == 2
    assert data["due_date"] == "2026-08-01"


async def test_update_todo_clear_due_date(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/todos/",
        json={"title": "Task", "due_date": "2026-08-01"},
    )
    todo_id = resp.json()["id"]

    resp = await client.patch(
        f"/api/todos/{todo_id}",
        json={"due_date": None},
    )
    assert resp.status_code == 200
    assert resp.json()["due_date"] is None


async def test_delete_todo(client: AsyncClient) -> None:
    resp = await client.post("/api/todos/", json={"title": "Delete me"})
    todo_id = resp.json()["id"]

    resp = await client.delete(f"/api/todos/{todo_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/api/todos/{todo_id}")
    assert resp.status_code == 404


async def test_filter_todos_by_completed(client: AsyncClient) -> None:
    await client.post("/api/todos/", json={"title": "Active"})
    create_resp = await client.post("/api/todos/", json={"title": "Done", "is_completed": True})
    done_id = create_resp.json()["id"]

    await client.patch(
        f"/api/todos/{done_id}",
        json={"is_completed": True},
    )

    resp = await client.get("/api/todos/", params={"completed": True})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_reorder_todos(client: AsyncClient) -> None:
    r1 = await client.post("/api/todos/", json={"title": "First"})
    r2 = await client.post("/api/todos/", json={"title": "Second"})
    id1 = r1.json()["id"]
    id2 = r2.json()["id"]

    resp = await client.patch(
        "/api/todos/reorder",
        json={"items": [
            {"id": id2, "position": 0},
            {"id": id1, "position": 1},
        ]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["id"] == id2
    assert data[0]["position"] == 0
    assert data[1]["id"] == id1
    assert data[1]["position"] == 1
