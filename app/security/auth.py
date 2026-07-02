"""Optional API-key authentication middleware.

When ``settings.api_key`` is set, non-browser requests must include the key
via ``Authorization: Bearer <key>`` or ``X-API-Key: <key>``. Browser requests
to the same-origin frontend (``Accept: text/html``) and the health endpoint
are always allowed so the SPA keeps working without a login screen.
"""

import hmac
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings

# Paths that never require auth: the SPA shell, static assets, health check,
# and the MCP endpoint (MCP clients authenticate out-of-band / via transport).
_PUBLIC_PATHS = {"/", "/health"}
_PUBLIC_PREFIXES = ("/static", "/mcp")


def _looks_like_browser(request: Request) -> bool:
    """True for same-origin browser navigation / SPA fetches from the frontend."""
    accept = request.headers.get("accept", "").lower()
    return "text/html" in accept


def _extract_key(request: Request) -> str | None:
    """Pull the presented API key from headers, or None if absent."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-api-key")


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Reject requests missing the configured API key (when enabled)."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not settings.api_key:
            return await call_next(request)

        path = request.url.path
        if path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES):
            return await call_next(request)
        if _looks_like_browser(request):
            return await call_next(request)

        presented = _extract_key(request)
        if presented and hmac.compare_digest(presented, settings.api_key):
            return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or missing API key"},
        )
