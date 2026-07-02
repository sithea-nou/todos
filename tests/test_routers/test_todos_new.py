"""Tests for the new REST endpoints: search/filter/pagination, stats, trash, restore."""

from datetime import date, timedelta
from uuid import uuid4

from httpx import AsyncClient


async def test_stats_endpoint(client: AsyncClient) -> None:
    await client.post("/api/todos/", json={"title": "A"})
    await client.post("/api/todos/", json={"title": "B", "is_completed": True})

    resp = await client.get("/api/todos/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["active"] == 1
    assert data["completed"] == 1


async def test_search_query(client: AsyncClient) -> None:
    await client.post("/api/todos/", json={"title": "Buy milk"})
    await client.post("/api/todos/", json={"title": "Walk dog"})

    resp = await client.get("/api/todos/", params={"q": "milk"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Buy milk"


async def test_filter_by_priority(client: AsyncClient) -> None:
    await client.post("/api/todos/", json={"title": "Low", "priority": 1})
    await client.post("/api/todos/", json={"title": "High", "priority": 3})

    resp = await client.get("/api/todos/", params={"priority": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["priority"] == 3


async def test_filter_by_tag(client: AsyncClient) -> None:
    await client.post("/api/todos/", json={"title": "A", "tags": "work,urgent"})
    await client.post("/api/todos/", json={"title": "B", "tags": "home"})

    resp = await client.get("/api/todos/", params={"tag": "work"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "A"


async def test_pagination(client: AsyncClient) -> None:
    for i in range(5):
        await client.post("/api/todos/", json={"title": f"T{i}"})

    resp = await client.get("/api/todos/", params={"limit": 2, "offset": 0})
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    resp2 = await client.get("/api/todos/", params={"limit": 2, "offset": 2})
    ids1 = {t["id"] for t in resp.json()}
    ids2 = {t["id"] for t in resp2.json()}
    assert ids1.isdisjoint(ids2)


async def test_delete_is_soft_and_appears_in_trash(client: AsyncClient) -> None:
    create = await client.post("/api/todos/", json={"title": "X"})
    todo_id = create.json()["id"]

    resp = await client.delete(f"/api/todos/{todo_id}")
    assert resp.status_code == 204

    # Gone from the active list...
    active = await client.get("/api/todos/")
    assert all(t["id"] != todo_id for t in active.json())

    # ...but present in trash.
    trash = await client.get("/api/todos/trash")
    assert trash.status_code == 200
    assert any(t["id"] == todo_id for t in trash.json())


async def test_restore_endpoint(client: AsyncClient) -> None:
    create = await client.post("/api/todos/", json={"title": "X"})
    todo_id = create.json()["id"]
    await client.delete(f"/api/todos/{todo_id}")

    resp = await client.post(f"/api/todos/{todo_id}/restore")
    assert resp.status_code == 200
    assert resp.json()["deleted_at"] is None

    # Back in the active list.
    active = await client.get("/api/todos/")
    assert any(t["id"] == todo_id for t in active.json())


async def test_restore_not_in_trash_returns_404(client: AsyncClient) -> None:
    create = await client.post("/api/todos/", json={"title": "X"})
    todo_id = create.json()["id"]
    # Not deleted: restore should 404.
    resp = await client.post(f"/api/todos/{todo_id}/restore")
    assert resp.status_code == 404


async def test_purge_endpoint(client: AsyncClient) -> None:
    create = await client.post("/api/todos/", json={"title": "X"})
    todo_id = create.json()["id"]
    await client.delete(f"/api/todos/{todo_id}")

    resp = await client.delete(f"/api/todos/{todo_id}/purge")
    assert resp.status_code == 204

    # Truly gone: not in trash, not restorable.
    trash = await client.get("/api/todos/trash")
    assert all(t["id"] != todo_id for t in trash.json())
    resp_restore = await client.post(f"/api/todos/{todo_id}/restore")
    assert resp_restore.status_code == 404


async def test_empty_trash_endpoint(client: AsyncClient) -> None:
    create = await client.post("/api/todos/", json={"title": "X"})
    await client.delete(f"/api/todos/{create.json()['id']}")

    resp = await client.delete("/api/todos/trash")
    assert resp.status_code == 200
    assert resp.json()["purged"] == 1

    trash = await client.get("/api/todos/trash")
    assert trash.json() == []


async def test_get_deleted_todo_returns_404(client: AsyncClient) -> None:
    create = await client.post("/api/todos/", json={"title": "X"})
    todo_id = create.json()["id"]
    await client.delete(f"/api/todos/{todo_id}")

    resp = await client.get(f"/api/todos/{todo_id}")
    assert resp.status_code == 404


async def test_update_deleted_todo_returns_404(client: AsyncClient) -> None:
    create = await client.post("/api/todos/", json={"title": "X"})
    todo_id = create.json()["id"]
    await client.delete(f"/api/todos/{todo_id}")

    resp = await client.patch(f"/api/todos/{todo_id}", json={"title": "new"})
    assert resp.status_code == 404


async def test_create_with_tags(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/todos/", json={"title": "Tagged", "tags": "work,urgent"}
    )
    assert resp.status_code == 201
    assert resp.json()["tags"] == "work,urgent"


async def test_update_tags(client: AsyncClient) -> None:
    create = await client.post("/api/todos/", json={"title": "X"})
    todo_id = create.json()["id"]

    resp = await client.patch(f"/api/todos/{todo_id}", json={"tags": "a,b"})
    assert resp.status_code == 200
    assert resp.json()["tags"] == "a,b"


async def test_clear_tags_with_null(client: AsyncClient) -> None:
    create = await client.post("/api/todos/", json={"title": "X", "tags": "a"})
    todo_id = create.json()["id"]

    resp = await client.patch(f"/api/todos/{todo_id}", json={"tags": None})
    assert resp.status_code == 200
    assert resp.json()["tags"] is None


async def test_stats_includes_overdue(client: AsyncClient) -> None:
    past = (date.today() - timedelta(days=3)).isoformat()
    await client.post("/api/todos/", json={"title": "Late", "due_date": past})

    resp = await client.get("/api/todos/stats")
    assert resp.json()["overdue"] == 1


async def test_list_trash_ordered_by_deleted_at_desc(client: AsyncClient) -> None:
    import time

    c1 = await client.post("/api/todos/", json={"title": "first"})
    await client.delete(f"/api/todos/{c1.json()['id']}")
    time.sleep(0.05)
    c2 = await client.post("/api/todos/", json={"title": "second"})
    await client.delete(f"/api/todos/{c2.json()['id']}")

    trash = (await client.get("/api/todos/trash")).json()
    assert len(trash) == 2
    assert trash[0]["title"] == "second"


async def test_purge_nonexistent_returns_404(client: AsyncClient) -> None:
    resp = await client.delete(f"/api/todos/{uuid4()}/purge")
    assert resp.status_code == 404
