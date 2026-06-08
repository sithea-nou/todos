"""Tests for the todo_service layer."""

from app.database import AsyncSession
from app.models.todo import TodoCreate, TodoUpdate
from app.services import todo_service


async def test_create_and_get_todo(session: AsyncSession) -> None:
    data = TodoCreate(title="Test", description="Desc")
    todo = await todo_service.create_todo(session, data)
    assert todo.id is not None
    assert todo.title == "Test"

    fetched = await todo_service.get_todo(session, todo.id)
    assert fetched is not None
    assert fetched.title == "Test"


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
