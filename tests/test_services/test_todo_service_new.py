"""Tests for the new todo service features: search, tags, pagination, stats, soft-delete."""

from datetime import date, timedelta

from app.database import AsyncSession
from app.models.todo import TodoCreate
from app.services import todo_service


async def test_search_by_title(session: AsyncSession) -> None:
    await todo_service.create_todo(session, TodoCreate(title="Buy milk"))
    await todo_service.create_todo(session, TodoCreate(title="Walk dog"))

    results = await todo_service.list_todos(session, q="milk")
    assert len(results) == 1
    assert results[0].title == "Buy milk"


async def test_search_is_case_insensitive_and_matches_description(session: AsyncSession) -> None:
    await todo_service.create_todo(
        session, TodoCreate(title="X", description="Important notes")
    )

    results = await todo_service.list_todos(session, q="IMPORTANT")
    assert len(results) == 1


async def test_filter_by_priority(session: AsyncSession) -> None:
    await todo_service.create_todo(session, TodoCreate(title="Low", priority=1))
    await todo_service.create_todo(session, TodoCreate(title="High", priority=3))

    results = await todo_service.list_todos(session, priority=3)
    assert len(results) == 1
    assert results[0].priority == 3


async def test_filter_by_tag(session: AsyncSession) -> None:
    await todo_service.create_todo(session, TodoCreate(title="A", tags="work,urgent"))
    await todo_service.create_todo(session, TodoCreate(title="B", tags="home"))
    await todo_service.create_todo(session, TodoCreate(title="C", tags="work,low"))

    work = await todo_service.list_todos(session, tag="work")
    assert {t.title for t in work} == {"A", "C"}

    urgent = await todo_service.list_todos(session, tag="urgent")
    assert {t.title for t in urgent} == {"A"}

    home = await todo_service.list_todos(session, tag="home")
    assert {t.title for t in home} == {"B"}


async def test_pagination(session: AsyncSession) -> None:
    for i in range(5):
        await todo_service.create_todo(session, TodoCreate(title=f"T{i}"))

    first = await todo_service.list_todos(session, limit=2, offset=0)
    second = await todo_service.list_todos(session, limit=2, offset=2)
    assert len(first) == 2
    assert len(second) == 2
    assert {t.id for t in first}.isdisjoint({t.id for t in second})


async def test_get_stats(session: AsyncSession) -> None:
    today = date.today()
    await todo_service.create_todo(session, TodoCreate(title="Active"))
    await todo_service.create_todo(
        session, TodoCreate(title="Overdue", due_date=today - timedelta(days=1))
    )
    await todo_service.create_todo(session, TodoCreate(title="Done", is_completed=True))
    await todo_service.create_todo(
        session, TodoCreate(title="High", priority=3, is_completed=True)
    )

    stats = await todo_service.get_stats(session)
    assert stats.total == 4
    assert stats.active == 2
    assert stats.completed == 2
    assert stats.overdue == 1
    assert stats.by_priority.get(3) == 1


# --- Soft delete / trash ---


async def test_delete_is_soft(session: AsyncSession) -> None:
    t = await todo_service.create_todo(session, TodoCreate(title="bye"))
    ok = await todo_service.delete_todo(session, t.id)
    assert ok is True

    # Active set excludes it...
    active = await todo_service.list_todos(session)
    assert len(active) == 0
    # ...get_todo returns None...
    assert await todo_service.get_todo(session, t.id) is None
    # ...but the row still exists in trash.
    trash = await todo_service.list_trash(session)
    assert len(trash) == 1
    assert trash[0].id == t.id
    assert trash[0].deleted_at is not None


async def test_delete_twice_is_false(session: AsyncSession) -> None:
    t = await todo_service.create_todo(session, TodoCreate(title="x"))
    assert await todo_service.delete_todo(session, t.id) is True
    assert await todo_service.delete_todo(session, t.id) is False


async def test_restore_todo(session: AsyncSession) -> None:
    t = await todo_service.create_todo(session, TodoCreate(title="x"))
    await todo_service.delete_todo(session, t.id)

    restored = await todo_service.restore_todo(session, t.id)
    assert restored is not None
    assert restored.deleted_at is None
    assert restored.title == "x"

    # Now visible in the active list again.
    active = await todo_service.list_todos(session)
    assert len(active) == 1


async def test_restore_not_in_trash_returns_none(session: AsyncSession) -> None:
    t = await todo_service.create_todo(session, TodoCreate(title="x"))
    # Not deleted yet — restore should fail.
    assert await todo_service.restore_todo(session, t.id) is None


async def test_purge_todo(session: AsyncSession) -> None:
    t = await todo_service.create_todo(session, TodoCreate(title="x"))
    await todo_service.delete_todo(session, t.id)

    assert await todo_service.purge_todo(session, t.id) is True
    assert await todo_service.purge_todo(session, t.id) is False
    assert await todo_service.list_trash(session) == []


async def test_empty_trash(session: AsyncSession) -> None:
    t1 = await todo_service.create_todo(session, TodoCreate(title="a"))
    t2 = await todo_service.create_todo(session, TodoCreate(title="b"))
    await todo_service.delete_todo(session, t1.id)
    await todo_service.delete_todo(session, t2.id)

    count = await todo_service.empty_trash(session)
    assert count == 2
    assert await todo_service.list_trash(session) == []


async def test_reorder_excludes_deleted(session: AsyncSession) -> None:
    t1 = await todo_service.create_todo(session, TodoCreate(title="A"))
    t2 = await todo_service.create_todo(session, TodoCreate(title="B"))
    await todo_service.delete_todo(session, t2.id)

    reordered = await todo_service.reorder_todos(session, [(t1.id, 5)])
    assert len(reordered) == 1
    assert reordered[0].id == t1.id


async def test_update_on_deleted_returns_none(session: AsyncSession) -> None:
    from app.models.todo import TodoUpdate

    t = await todo_service.create_todo(session, TodoCreate(title="x"))
    await todo_service.delete_todo(session, t.id)

    result = await todo_service.update_todo(session, t.id, TodoUpdate(title="new"))
    assert result is None


async def test_tags_round_trip(session: AsyncSession) -> None:
    t = await todo_service.create_todo(session, TodoCreate(title="X", tags="a,b"))
    assert t.tags == "a,b"
    fetched = await todo_service.get_todo(session, t.id)
    assert fetched is not None
    assert fetched.tags == "a,b"
