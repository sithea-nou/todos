"""Tests for the optional API-key auth and rate-limit middleware."""

from unittest.mock import patch

from httpx import AsyncClient

from app.config import settings


async def test_no_auth_when_api_key_unset(client: AsyncClient) -> None:
    """With API_KEY empty (default) all endpoints are open."""
    with patch.object(settings, "api_key", ""):
        resp = await client.get("/api/todos/")
    assert resp.status_code == 200


async def test_auth_rejects_missing_key(client: AsyncClient) -> None:
    with patch.object(settings, "api_key", "secret-key"):
        resp = await client.get("/api/todos/")
    assert resp.status_code == 401
    assert "API key" in resp.json()["detail"]


async def test_auth_accepts_bearer_token(client: AsyncClient) -> None:
    with patch.object(settings, "api_key", "secret-key"):
        resp = await client.get(
            "/api/todos/",
            headers={"Authorization": "Bearer secret-key"},
        )
    assert resp.status_code == 200


async def test_auth_accepts_x_api_key_header(client: AsyncClient) -> None:
    with patch.object(settings, "api_key", "secret-key"):
        resp = await client.get(
            "/api/todos/", headers={"X-API-Key": "secret-key"}
        )
    assert resp.status_code == 200


async def test_auth_rejects_wrong_key(client: AsyncClient) -> None:
    with patch.object(settings, "api_key", "secret-key"):
        resp = await client.get(
            "/api/todos/", headers={"Authorization": "Bearer wrong"}
        )
    assert resp.status_code == 401


async def test_auth_allows_public_paths_without_key(client: AsyncClient) -> None:
    """Health and the SPA shell stay open even when auth is on."""
    with patch.object(settings, "api_key", "secret-key"):
        health = await client.get("/health")
        assert health.status_code == 200
        root = await client.get("/", headers={"Accept": "text/html"})
        assert root.status_code == 200


async def test_auth_allows_browser_requests(client: AsyncClient) -> None:
    """A request that looks like a browser (Accept: text/html) is allowed."""
    with patch.object(settings, "api_key", "secret-key"):
        resp = await client.get(
            "/api/todos/", headers={"Accept": "text/html"}
        )
    # The endpoint returns JSON regardless; auth just doesn't block it.
    assert resp.status_code == 200


async def test_rate_limit_rejects_after_limit(client: AsyncClient) -> None:
    with patch.object(settings, "chat_rate_limit", 2):
        # Two requests allowed, third is rejected.
        r1 = await client.get("/api/chat/info")
        r2 = await client.get("/api/chat/info")
        r3 = await client.get("/api/chat/info")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert "Retry-After" in r3.headers


async def test_rate_limit_does_not_affect_todos(client: AsyncClient) -> None:
    with patch.object(settings, "chat_rate_limit", 1):
        # todos endpoint is not under /api/chat, so it's never throttled.
        for _ in range(5):
            resp = await client.get("/api/todos/")
            assert resp.status_code == 200


async def test_rate_limit_disabled_by_default(client: AsyncClient) -> None:
    with patch.object(settings, "chat_rate_limit", 0):
        for _ in range(20):
            resp = await client.get("/api/chat/info")
            assert resp.status_code == 200
