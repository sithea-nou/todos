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
    assert "id" in data
    assert "created_at" in data


async def test_list_todos(client: AsyncClient) -> None:
    # Create two todos
    await client.post("/api/todos/", json={"title": "First"})
    await client.post("/api/todos/", json={"title": "Second"})

    resp = await client.get("/api/todos/")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


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
