"""Database engine, session, and FastAPI dependency."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.config import settings

engine = create_async_engine(settings.database_url, echo=settings.debug)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator:
    """Yield an async database session."""
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    """Create all tables defined by SQLModel."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
