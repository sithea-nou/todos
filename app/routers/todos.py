"""Todo CRUD API routes."""

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import get_todo_or_404
from app.models.todo import ReorderRequest, TodoCreate, TodoRead, TodoUpdate
from app.services import todo_service

router = APIRouter()


@router.get("/", response_model=list[TodoRead])
async def list_todos(
    session: AsyncSession = Depends(get_session),
    completed: bool | None = Query(default=None),
    order_by: str = Query(default="position"),
) -> list[TodoRead]:
    """List all todos, optionally filtered by completion status and ordered."""
    allowed = {"position", "priority", "due_date"}
    if order_by not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"order_by must be one of {sorted(allowed)}",
        )
    todos = await todo_service.list_todos(session, completed=completed, order_by=order_by)
    return todos


@router.post("/", response_model=TodoRead, status_code=201)
async def create_todo(
    data: TodoCreate,
    session: AsyncSession = Depends(get_session),
) -> TodoRead:
    """Create a new todo."""
    todo = await todo_service.create_todo(session, data)
    return todo


@router.patch("/reorder", response_model=list[TodoRead])
async def reorder_todos(
    data: ReorderRequest,
    session: AsyncSession = Depends(get_session),
) -> list[TodoRead]:
    """Batch-reorder todos by updating their positions."""
    items = [(item.id, item.position) for item in data.items]
    return await todo_service.reorder_todos(session, items)


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
    """Delete a todo."""
    await todo_service.delete_todo(session, todo_id)
