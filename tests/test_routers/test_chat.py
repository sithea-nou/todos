"""Tests for the chat router."""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient


async def test_chat_returns_response(client: AsyncClient) -> None:
    with patch("app.services.chat_service.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "Hello!"
        resp = await client.post("/api/chat/", json={"message": "Hi"})
    assert resp.status_code == 200
    assert resp.json() == {"response": "Hello!"}
    mock_chat.assert_awaited_once_with("Hi", [])


async def test_chat_passes_history(client: AsyncClient) -> None:
    history = [{"role": "user", "content": "prev"}]
    with patch("app.services.chat_service.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "ok"
        resp = await client.post("/api/chat/", json={"message": "next", "history": history})
    assert resp.status_code == 200
    mock_chat.assert_awaited_once_with("next", history)


async def test_chat_missing_message_returns_422(client: AsyncClient) -> None:
    resp = await client.post("/api/chat/", json={})
    assert resp.status_code == 422
