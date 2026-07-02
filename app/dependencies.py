"""Reusable FastAPI dependencies."""

from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.services import todo_service


async def get_todo_or_404(
    todo_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> object:
    """Fetch an active (non-deleted) todo or raise 404."""
    todo = await todo_service.get_todo(session, todo_id)
    if todo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found")
    return todo
