"""SQLModel ORM models for Todo items."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class TodoBase(SQLModel):
    """Shared Todo fields."""

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    is_completed: bool = Field(default=False)
    priority: int = Field(default=0, ge=0)
    due_date: date | None = Field(default=None)
    tags: str | None = Field(default=None, max_length=500)  # comma-separated


class Todo(TodoBase, table=True):
    """Todo ORM model."""

    __tablename__ = "todos"

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    position: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    deleted_at: datetime | None = Field(default=None)  # soft-delete timestamp


class TodoCreate(TodoBase):
    """Schema for creating a Todo."""

    pass


class TodoUpdate(SQLModel):
    """Schema for updating a Todo (all fields optional).

    Pass ``tags=None`` to clear tags. Use ``due_date=None`` to clear the date.
    """

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    is_completed: bool | None = None
    priority: int | None = None
    due_date: date | None = None
    tags: str | None = None


class TodoRead(TodoBase):
    """Schema for reading a Todo (includes id, position, and timestamps)."""

    id: UUID
    position: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class TodoStats(SQLModel):
    """Aggregate counts describing the active todo set."""

    total: int = 0
    active: int = 0
    completed: int = 0
    overdue: int = 0
    by_priority: dict[int, int] = Field(default_factory=dict)


class ReorderItem(SQLModel):
    """A single item in a reorder request."""

    id: UUID
    position: int


class ReorderRequest(SQLModel):
    """Batch reorder request: list of (id, new_position) pairs."""

    items: list[ReorderItem]
