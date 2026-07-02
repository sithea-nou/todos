"""Todo CRUD API routes."""

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import get_todo_or_404
from app.models.todo import ReorderRequest, TodoCreate, TodoRead, TodoStats, TodoUpdate
from app.services import todo_service

router = APIRouter()


@router.get("/stats", response_model=TodoStats)
async def get_stats(
    session: AsyncSession = Depends(get_session),
) -> TodoStats:
    """Return aggregate counts (total / active / completed / overdue / by priority)."""
    return await todo_service.get_stats(session)


@router.get("/", response_model=list[TodoRead])
async def list_todos(
    session: AsyncSession = Depends(get_session),
    completed: bool | None = Query(default=None),
    order_by: str = Query(default="position"),
    q: str | None = Query(default=None, description="Substring search over title + description"),
    priority: int | None = Query(default=None, ge=0, description="Filter by exact priority"),
    tag: str | None = Query(
        default=None, description="Filter by tag token (tags are comma-separated)"
    ),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int | None = Query(default=None, ge=0),
) -> list[TodoRead]:
    """List todos, optionally filtered, searched, paginated, and ordered."""
    allowed = {"position", "priority", "due_date"}
    if order_by not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"order_by must be one of {sorted(allowed)}",
        )
    return await todo_service.list_todos(
        session,
        completed=completed,
        order_by=order_by,
        q=q,
        priority=priority,
        tag=tag,
        limit=limit,
        offset=offset,
    )


@router.post("/", response_model=TodoRead, status_code=201)
async def create_todo(
    data: TodoCreate,
    session: AsyncSession = Depends(get_session),
) -> TodoRead:
    """Create a new todo."""
    return await todo_service.create_todo(session, data)


@router.patch("/reorder", response_model=list[TodoRead])
async def reorder_todos(
    data: ReorderRequest,
    session: AsyncSession = Depends(get_session),
) -> list[TodoRead]:
    """Batch-reorder todos by updating their positions."""
    items = [(item.id, item.position) for item in data.items]
    return await todo_service.reorder_todos(session, items)


@router.get("/trash", response_model=list[TodoRead])
async def list_trash(
    session: AsyncSession = Depends(get_session),
) -> list[TodoRead]:
    """List soft-deleted todos (newest-deleted first)."""
    return await todo_service.list_trash(session)


@router.delete("/trash", status_code=200)
async def empty_trash(
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    """Permanently delete every soft-deleted todo."""
    count = await todo_service.empty_trash(session)
    return {"purged": count}


@router.post("/{todo_id}/restore", response_model=TodoRead)
async def restore_todo(
    todo_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> TodoRead:
    """Restore a soft-deleted todo."""
    restored = await todo_service.restore_todo(session, todo_id)
    if restored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Todo not found in trash",
        )
    return restored


@router.delete("/{todo_id}/purge", status_code=204)
async def purge_todo(
    todo_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Permanently delete a single todo row (e.g. from the trash)."""
    purged = await todo_service.purge_todo(session, todo_id)
    if not purged:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Todo not found",
        )


@router.get("/{todo_id}", response_model=TodoRead)
async def get_todo(
    todo_id: UUID,
    _todo: object = Depends(get_todo_or_404),
) -> TodoRead:
    """Get a single todo by ID."""
    return cast(TodoRead, _todo)


@router.patch("/{todo_id}", response_model=TodoRead)
async def update_todo(
    todo_id: UUID,
    data: TodoUpdate,
    session: AsyncSession = Depends(get_session),
    _todo: object = Depends(get_todo_or_404),
) -> TodoRead:
    """Update an existing todo."""
    updated = await todo_service.update_todo(session, todo_id, data)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update todo",
        )
    return updated


@router.delete("/{todo_id}", status_code=204)
async def delete_todo(
    todo_id: UUID,
    session: AsyncSession = Depends(get_session),
    _todo: object = Depends(get_todo_or_404),
) -> None:
    """Soft-delete a todo (movable to trash; restore later)."""
    await todo_service.delete_todo(session, todo_id)
