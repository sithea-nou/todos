"""Todo business logic and repository layer."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.models.todo import Todo, TodoCreate, TodoRead, TodoStats, TodoUpdate


def _to_read(todo: Todo) -> TodoRead:
    """Round-trip an ORM row through a TodoRead schema."""
    return TodoRead(**todo.model_dump())


async def list_todos(
    session: AsyncSession,
    completed: bool | None = None,
    order_by: str = "position",
    q: str | None = None,
    priority: int | None = None,
    tag: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
    include_deleted: bool = False,
) -> list[TodoRead]:
    """List todos with optional filtering, search, pagination, and ordering.

    By default soft-deleted todos are excluded; pass ``include_deleted=True``
    (or use :func:`list_trash`) to see them.
    """
    stmt = select(Todo)

    if not include_deleted:
        stmt = stmt.where(col(Todo.deleted_at).is_(None))

    if completed is not None:
        stmt = stmt.where(Todo.is_completed == completed)

    if priority is not None:
        stmt = stmt.where(Todo.priority == priority)

    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Todo.title).like(like),
                func.lower(func.coalesce(Todo.description, "")).like(like),
            )
        )

    if tag:
        # Tags are stored comma-separated; match the tag as a whole token.
        t = tag.lower()
        stmt = stmt.where(
            or_(
                func.lower(func.coalesce(Todo.tags, "")) == t,
                func.lower(func.coalesce(Todo.tags, "")).like(f"{t},%"),
                func.lower(func.coalesce(Todo.tags, "")).like(f"%,{t}"),
                func.lower(func.coalesce(Todo.tags, "")).like(f"%,{t},%"),
            )
        )

    if order_by == "priority":
        stmt = stmt.order_by(col(Todo.priority).desc(), col(Todo.created_at).asc())
    elif order_by == "due_date":
        stmt = stmt.order_by(
            col(Todo.due_date).asc().nulls_last(), col(Todo.created_at).asc()
        )
    else:
        stmt = stmt.order_by(col(Todo.position).asc(), col(Todo.created_at).asc())

    if limit is not None:
        stmt = stmt.limit(limit)
    if offset is not None:
        stmt = stmt.offset(offset)

    result = await session.execute(stmt)
    todos = result.scalars().all()
    return [_to_read(todo) for todo in todos]


async def get_todo(
    session: AsyncSession,
    todo_id: UUID,
    include_deleted: bool = False,
) -> TodoRead | None:
    """Fetch a single todo by ID.

    Returns ``None`` if the row doesn't exist or (by default) has been
    soft-deleted.
    """
    todo = await session.get(Todo, todo_id)
    if todo is None:
        return None
    if todo.deleted_at is not None and not include_deleted:
        return None
    return _to_read(todo)


async def create_todo(session: AsyncSession, data: TodoCreate) -> TodoRead:
    """Create a new todo with auto-assigned position."""
    count_result = await session.execute(
        select(func.count()).select_from(Todo).where(
            col(Todo.deleted_at).is_(None)
        )
    )
    next_position = count_result.scalar() or 0

    todo = Todo(**data.model_dump(), position=next_position)
    session.add(todo)
    await session.commit()
    await session.refresh(todo)
    return _to_read(todo)


async def update_todo(session: AsyncSession, todo_id: UUID, data: TodoUpdate) -> TodoRead | None:
    """Update an existing (non-deleted) todo."""
    todo = await session.get(Todo, todo_id)
    if todo is None or todo.deleted_at is not None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(todo, key, value)
    todo.updated_at = datetime.now()

    await session.commit()
    await session.refresh(todo)

    return _to_read(todo)


async def delete_todo(session: AsyncSession, todo_id: UUID) -> bool:
    """Soft-delete a todo. Returns True if soft-deleted, False if not found."""
    todo = await session.get(Todo, todo_id)
    if todo is None or todo.deleted_at is not None:
        return False
    todo.deleted_at = datetime.now()
    await session.commit()
    return True


async def restore_todo(session: AsyncSession, todo_id: UUID) -> TodoRead | None:
    """Restore a soft-deleted todo. Returns the restored todo or ``None``."""
    todo = await session.get(Todo, todo_id)
    if todo is None or todo.deleted_at is None:
        return None
    todo.deleted_at = None
    todo.updated_at = datetime.now()
    await session.commit()
    await session.refresh(todo)
    return _to_read(todo)


async def purge_todo(session: AsyncSession, todo_id: UUID) -> bool:
    """Permanently delete a todo row. Returns True if purged, False if absent."""
    todo = await session.get(Todo, todo_id)
    if todo is None:
        return False
    await session.delete(todo)
    await session.commit()
    return True


async def list_trash(session: AsyncSession) -> list[TodoRead]:
    """List all soft-deleted todos, newest-deleted first."""
    stmt = (
        select(Todo)
        .where(col(Todo.deleted_at).is_not(None))
        .order_by(col(Todo.deleted_at).desc())
    )
    result = await session.execute(stmt)
    return [_to_read(t) for t in result.scalars().all()]


async def empty_trash(session: AsyncSession) -> int:
    """Permanently delete every soft-deleted todo. Returns the count removed."""
    stmt = select(Todo).where(col(Todo.deleted_at).is_not(None))
    result = await session.execute(stmt)
    count = 0
    for todo in result.scalars().all():
        await session.delete(todo)
        count += 1
    if count:
        await session.commit()
    return count


async def reorder_todos(
    session: AsyncSession,
    items: list[tuple[UUID, int]],
) -> list[TodoRead]:
    """Batch-update positions for todos. Returns the active list re-ordered."""
    for todo_id, position in items:
        todo = await session.get(Todo, todo_id)
        if todo is not None and todo.deleted_at is None:
            todo.position = position
    await session.commit()

    result = await session.execute(
        select(Todo)
        .where(col(Todo.deleted_at).is_(None))
        .order_by(col(Todo.position).asc(), col(Todo.created_at).asc())
    )
    return [_to_read(todo) for todo in result.scalars().all()]


async def get_stats(session: AsyncSession) -> TodoStats:
    """Return aggregate counts over the active (non-deleted) todo set."""
    base = select(Todo).where(col(Todo.deleted_at).is_(None))
    result = await session.execute(base)
    todos = result.scalars().all()

    today = date.today()
    by_priority: dict[int, int] = {}
    active = completed = overdue = 0
    for t in todos:
        if t.is_completed:
            completed += 1
        else:
            active += 1
            if t.due_date is not None and t.due_date < today:
                overdue += 1
        by_priority[t.priority] = by_priority.get(t.priority, 0) + 1

    return TodoStats(
        total=len(todos),
        active=active,
        completed=completed,
        overdue=overdue,
        by_priority=by_priority,
    )
