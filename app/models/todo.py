"""SQLModel ORM models for Todo items."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class TodoBase(SQLModel):
    """Shared Todo fields."""

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    is_completed: bool = Field(default=False)


class Todo(TodoBase, table=True):
    """Todo ORM model."""

    __tablename__ = "todos"

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class TodoCreate(TodoBase):
    """Schema for creating a Todo."""

    pass


class TodoUpdate(SQLModel):
    """Schema for updating a Todo (all fields optional)."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    is_completed: bool | None = None


class TodoRead(TodoBase):
    """Schema for reading a Todo (includes id and timestamps)."""

    id: UUID
    created_at: datetime
    updated_at: datetime
