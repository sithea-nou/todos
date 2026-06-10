"""Todo business logic and repository layer."""

from uuid import UUID

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.models.todo import Todo, TodoCreate, TodoRead, TodoUpdate


async def list_todos(
    session: AsyncSession,
    completed: bool | None = None,
    order_by: str = "position",
) -> list[TodoRead]:
    """List todos, optionally filtering by completion status and ordering."""
    stmt = select(Todo)

    if completed is not None:
        stmt = stmt.where(Todo.is_completed == completed)

    if order_by == "priority":
        stmt = stmt.order_by(col(Todo.priority).desc(), col(Todo.created_at).asc())
    elif order_by == "due_date":
        stmt = stmt.order_by(
            col(Todo.due_date).asc().nulls_last(), col(Todo.created_at).asc()
        )
    else:
        stmt = stmt.order_by(col(Todo.position).asc(), col(Todo.created_at).asc())

    result = await session.execute(stmt)
    todos = result.scalars().all()
    return [TodoRead(**todo.model_dump()) for todo in todos]


async def get_todo(session: AsyncSession, todo_id: UUID) -> TodoRead | None:
    """Fetch a single todo by ID."""
    todo = await session.get(Todo, todo_id)
    return TodoRead(**todo.model_dump()) if todo else None


async def create_todo(session: AsyncSession, data: TodoCreate) -> TodoRead:
    """Create a new todo with auto-assigned position."""
    count_result = await session.execute(
        select(func.count()).select_from(Todo)
    )
    next_position = count_result.scalar() or 0

    todo = Todo(**data.model_dump(), position=next_position)
    session.add(todo)
    await session.commit()
    await session.refresh(todo)
    return TodoRead(**todo.model_dump())


async def update_todo(session: AsyncSession, todo_id: UUID, data: TodoUpdate) -> TodoRead | None:
    """Update an existing todo."""
    todo = await session.get(Todo, todo_id)
    if todo is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(todo, key, value)

    await session.commit()
    await session.refresh(todo)

    return TodoRead(**todo.model_dump())


async def delete_todo(session: AsyncSession, todo_id: UUID) -> bool:
    """Delete a todo. Returns True if deleted, False if not found."""
    todo = await session.get(Todo, todo_id)
    if todo is None:
        return False
    await session.delete(todo)
    await session.commit()
    return True


async def reorder_todos(
    session: AsyncSession,
    items: list[tuple[UUID, int]],
) -> list[TodoRead]:
    """Batch-update positions for todos. Returns the updated list."""
    for todo_id, position in items:
        todo = await session.get(Todo, todo_id)
        if todo is not None:
            todo.position = position
    await session.commit()

    result = await session.execute(
        select(Todo).order_by(col(Todo.position).asc(), col(Todo.created_at).asc())
    )
    todos = result.scalars().all()
    return [TodoRead(**todo.model_dump()) for todo in todos]
