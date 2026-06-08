"""Shared test fixtures for async database sessions."""

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import delete

from app.database import AsyncSession, async_session_factory
from app.models.todo import Todo


@pytest_asyncio.fixture
async def session() -> AsyncGenerator:
    """Provide a test database session with auto-cleanup."""
    async with async_session_factory() as s:
        yield s
        # Clean up test data
        await s.exec(delete(Todo))
        await s.commit()


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncGenerator:
    """Provide an async test client bound to the test session."""
    from app.main import app

    app.dependency_overrides[async_session_factory] = lambda: session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
