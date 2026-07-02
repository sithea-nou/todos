"""Database engine, session, and FastAPI dependency."""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=settings.debug)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def _migrate_columns() -> None:
    """Add new columns to existing tables if they don't exist yet."""
    migrations = [
        ("todos", "priority", "INTEGER DEFAULT 0"),
        ("todos", "due_date", "DATE"),
        ("todos", "position", "INTEGER DEFAULT 0"),
        ("todos", "tags", "VARCHAR(500)"),
        ("todos", "deleted_at", "DATETIME"),
    ]
    async with engine.begin() as conn:
        for table, column, col_type in migrations:
            try:
                await conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                )
                logger.info("Added column %s.%s", table, column)
            except Exception:
                pass


async def get_session() -> AsyncGenerator[AsyncSession]:
    """Yield an async database session."""
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    """Create all tables defined by SQLModel and migrate existing ones."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await _migrate_columns()
