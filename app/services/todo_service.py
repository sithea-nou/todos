"""Todo business logic and repository layer."""

from uuid import UUID

from sqlmodel import select

from app.database import AsyncSession
from app.models.todo import Todo, TodoCreate, TodoRead, TodoUpdate


async def list_todos(session: AsyncSession, completed: bool | None = None) -> list[TodoRead]:
    """List todos, optionally filtering by completion status."""
    stmt = select(Todo)
    if completed is not None:
        stmt = stmt.where(Todo.is_completed == completed)
    result = await session.execute(stmt)
    todos = result.scalars().all()
    return [TodoRead(**todo.model_dump()) for todo in todos]


async def get_todo(session: AsyncSession, todo_id: UUID) -> TodoRead | None:
    """Fetch a single todo by ID."""
    todo = await session.get(Todo, todo_id)
    return TodoRead(**todo.model_dump()) if todo else None


async def create_todo(session: AsyncSession, data: TodoCreate) -> TodoRead:
    """Create a new todo."""
    todo = Todo(**data.model_dump())
    session.add(todo)
    await session.commit()
    await session.refresh(todo)
    return TodoRead(**todo.model_dump())


async def update_todo(session: AsyncSession, todo_id: UUID, data: TodoUpdate) -> TodoRead | None:
    """Update an existing todo."""
    # Get the raw model (not the schema)
    todo = await session.get(Todo, todo_id)
    if todo is None:
        return None

    # Update the model's attributes directly
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(todo, key, value)

    await session.commit()
    await session.refresh(todo)

    # Convert to schema for return
    return TodoRead(**todo.model_dump())


async def delete_todo(session: AsyncSession, todo_id: UUID) -> bool:
    """Delete a todo. Returns True if deleted, False if not found."""
    # Get the raw model (not the schema) - we need the ORM model for deletion
    todo = await session.get(Todo, todo_id)
    if todo is None:
        return False
    await session.delete(todo)
    await session.commit()
    return True
