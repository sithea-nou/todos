"""Shared test fixtures for async database sessions."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest_asyncio
from fastmcp import Client
from httpx import ASGITransport, AsyncClient
from sqlmodel import delete

import app.mcp_server
from app.database import AsyncSession, async_session_factory
from app.mcp_server import mcp
from app.models.chat import ChatMessage, ChatSession
from app.models.todo import Todo


@pytest_asyncio.fixture(scope="session", autouse=True)
async def init_database() -> AsyncGenerator:
    """Create database tables before tests and clean up after."""
    from app.database import init_db

    # Create all tables
    await init_db()

    yield

    # Optional: cleanup after all tests
    pass


@pytest_asyncio.fixture
async def session() -> AsyncGenerator:
    """Provide a test database session with auto-cleanup."""
    async with async_session_factory() as s:
        # Wipe any rows left by a prior failed/interrupted run before starting.
        await s.execute(delete(ChatMessage))
        await s.execute(delete(ChatSession))
        await s.execute(delete(Todo))
        await s.commit()
        yield s
        await s.execute(delete(ChatMessage))
        await s.execute(delete(ChatSession))
        await s.execute(delete(Todo))
        await s.commit()


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncGenerator:
    """Provide an async test client bound to the test session."""
    from app.main import app as fastapi_app

    fastapi_app.dependency_overrides[async_session_factory] = lambda: session

    # Chat service routes tool execution through the MCP server, so we patch
    # the MCP server's session factory (same approach as the mcp_client fixture).
    original_mcp_factory = app.mcp_server.async_session_factory

    @asynccontextmanager
    async def _cs_factory():
        yield session

    app.mcp_server.async_session_factory = _cs_factory  # type: ignore[assignment]
    try:
        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.mcp_server.async_session_factory = original_mcp_factory  # type: ignore[assignment]


@pytest_asyncio.fixture
async def mcp_client(session: AsyncSession) -> AsyncGenerator:
    """FastMCP Client bound to the test session.

    Monkeypatches `app.mcp_server.async_session_factory` so MCP tools reuse
    the per-test session. Cleanup is handled by the `session` fixture's
    teardown (deletes all Todo rows after the test).
    """
    @asynccontextmanager
    async def _test_factory():
        yield session

    original = app.mcp_server.async_session_factory
    app.mcp_server.async_session_factory = _test_factory
    try:
        client = Client(mcp)
        async with client:
            yield client
    finally:
        app.mcp_server.async_session_factory = original
