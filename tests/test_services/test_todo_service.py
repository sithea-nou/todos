"""Tests for the todo_service layer."""

from app.database import AsyncSession
from app.models.todo import TodoCreate, TodoUpdate
from app.services import todo_service


async def test_create_and_get_todo(session: AsyncSession) -> None:
    data = TodoCreate(title="Test", description="Desc")
    todo = await todo_service.create_todo(session, data)
    assert todo.id is not None
    assert todo.title == "Test"
    assert todo.position == 0

    fetched = await todo_service.get_todo(session, todo.id)
    assert fetched is not None
    assert fetched.title == "Test"


async def test_create_todo_auto_positions(session: AsyncSession) -> None:
    t1 = await todo_service.create_todo(session, TodoCreate(title="First"))
    t2 = await todo_service.create_todo(session, TodoCreate(title="Second"))
    assert t1.position == 0
    assert t2.position == 1


async def test_create_todo_with_priority_and_due_date(session: AsyncSession) -> None:
    from datetime import date

    data = TodoCreate(title="Priority task", priority=3, due_date=date(2026, 7, 15))
    todo = await todo_service.create_todo(session, data)
    assert todo.priority == 3
    assert todo.due_date == date(2026, 7, 15)


async def test_update_todo(session: AsyncSession) -> None:
    data = TodoCreate(title="Original")
    todo = await todo_service.create_todo(session, data)

    updated = await todo_service.update_todo(
        session,
        todo.id,
        TodoUpdate(title="Updated"),
    )
    assert updated is not None
    assert updated.title == "Updated"


async def test_update_todo_priority_and_due_date(session: AsyncSession) -> None:
    from datetime import date

    data = TodoCreate(title="Task")
    todo = await todo_service.create_todo(session, data)

    updated = await todo_service.update_todo(
        session,
        todo.id,
        TodoUpdate(priority=2, due_date=date(2026, 8, 1)),
    )
    assert updated is not None
    assert updated.priority == 2
    assert updated.due_date == date(2026, 8, 1)


async def test_delete_todo(session: AsyncSession) -> None:
    data = TodoCreate(title="To delete")
    todo = await todo_service.create_todo(session, data)

    result = await todo_service.delete_todo(session, todo.id)
    assert result is True

    result = await todo_service.delete_todo(session, todo.id)
    assert result is False


async def test_list_todos(session: AsyncSession) -> None:
    await todo_service.create_todo(session, TodoCreate(title="A"))
    await todo_service.create_todo(session, TodoCreate(title="B"))

    todos = await todo_service.list_todos(session)
    assert len(todos) == 2


async def test_list_todos_filter_completed(session: AsyncSession) -> None:
    await todo_service.create_todo(session, TodoCreate(title="Active"))
    await todo_service.create_todo(session, TodoCreate(title="Done", is_completed=True))

    done = await todo_service.list_todos(session, completed=True)
    assert len(done) == 1
    assert done[0].title == "Done"


async def test_list_todos_order_by_position(session: AsyncSession) -> None:
    await todo_service.create_todo(session, TodoCreate(title="A"))
    await todo_service.create_todo(session, TodoCreate(title="B"))

    todos = await todo_service.list_todos(session, order_by="position")
    assert len(todos) == 2
    assert todos[0].position <= todos[1].position


async def test_list_todos_order_by_priority(session: AsyncSession) -> None:
    await todo_service.create_todo(session, TodoCreate(title="Low", priority=1))
    await todo_service.create_todo(session, TodoCreate(title="High", priority=3))

    todos = await todo_service.list_todos(session, order_by="priority")
    assert len(todos) == 2
    assert todos[0].priority >= todos[1].priority


async def test_list_todos_order_by_due_date(session: AsyncSession) -> None:
    from datetime import date

    await todo_service.create_todo(
        session, TodoCreate(title="Later", due_date=date(2026, 12, 1))
    )
    await todo_service.create_todo(
        session, TodoCreate(title="Sooner", due_date=date(2026, 6, 1))
    )

    todos = await todo_service.list_todos(session, order_by="due_date")
    assert len(todos) == 2
    assert todos[0].due_date is not None
    assert todos[1].due_date is not None
    assert todos[0].due_date <= todos[1].due_date


async def test_reorder_todos(session: AsyncSession) -> None:
    t1 = await todo_service.create_todo(session, TodoCreate(title="A"))
    t2 = await todo_service.create_todo(session, TodoCreate(title="B"))

    reordered = await todo_service.reorder_todos(session, [(t2.id, 0), (t1.id, 1)])
    assert len(reordered) >= 2
