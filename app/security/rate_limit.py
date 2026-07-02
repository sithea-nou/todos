"""Simple in-memory per-client rate limiter (token bucket per minute).

Applies only to the chat endpoints (which call a paid LLM). Uses an in-memory
dict keyed by client IP; each client gets ``limit`` tokens per 60s window.
A ``chat_rate_limit`` of 0 disables limiting (the default).
"""

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.config import settings

_WINDOW = 60.0  # seconds


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Limit requests per client IP to chat endpoints."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._hits: dict[str, list[float]] = {}

    def _client(self, request: Request) -> str:
        # Honour X-Forwarded-For when present, else fall back to direct client.
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        limit = settings.chat_rate_limit
        if limit <= 0 or not request.url.path.startswith("/api/chat"):
            return await call_next(request)

        client = self._client(request)
        now = time.monotonic()
        window_start = now - _WINDOW
        hits = self._hits.setdefault(client, [])
        # Drop timestamps outside the current window.
        self._hits[client] = [t for t in hits if t > window_start]
        if len(self._hits[client]) >= limit:
            retry = int(_WINDOW - (now - self._hits[client][0])) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(max(retry, 1))},
            )
        self._hits[client].append(now)
        return await call_next(request)
