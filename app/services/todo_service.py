"""Todo business logic and repository layer."""

from uuid import UUID

from sqlmodel import select

from app.database import AsyncSession
from app.models.todo import Todo, TodoCreate, TodoUpdate


async def list_todos(session: AsyncSession, completed: bool | None = None) -> list[Todo]:
    """List todos, optionally filtering by completion status."""
    stmt = select(Todo)
    if completed is not None:
        stmt = stmt.where(Todo.is_completed == completed)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_todo(session: AsyncSession, todo_id: UUID) -> Todo | None:
    """Fetch a single todo by ID."""
    return await session.get(Todo, todo_id)


async def create_todo(session: AsyncSession, data: TodoCreate) -> Todo:
    """Create a new todo."""
    todo = Todo(**data.model_dump())
    session.add(todo)
    await session.commit()
    await session.refresh(todo)
    return todo


async def update_todo(session: AsyncSession, todo_id: UUID, data: TodoUpdate) -> Todo | None:
    """Update an existing todo."""
    todo = await get_todo(session, todo_id)
    if todo is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(todo, key, value)
    await session.commit()
    await session.refresh(todo)
    return todo


async def delete_todo(session: AsyncSession, todo_id: UUID) -> bool:
    """Delete a todo. Returns True if deleted, False if not found."""
    todo = await get_todo(session, todo_id)
    if todo is None:
        return False
    await session.delete(todo)
    await session.commit()
    return True
