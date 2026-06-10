"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastmcp.utilities.lifespan import combine_lifespans

from app.config import settings
from app.database import init_db
from app.mcp_server import mcp
from app.routers import chat, chat_sessions, todos

# Configure logging based on DEBUG_LOGGING setting
if settings.debug_logging:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Database init on startup, cleanup on shutdown."""
    await init_db()
    yield


mcp_app = mcp.http_app(path="/", transport="http")

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan),
)

app.include_router(todos.router, prefix="/api/todos", tags=["todos"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(chat_sessions.router, prefix="/api/chat", tags=["chat-sessions"])


@app.get("/")
async def serve_frontend() -> HTMLResponse:
    """Serve the frontend HTML."""
    html_path = Path(__file__).parent.parent / "index.html"
    return HTMLResponse(content=html_path.read_text())


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "app": settings.app_name}

# Mount sub-apps and static files after routes
app.mount("/mcp", mcp_app)
app.mount("/static", StaticFiles(directory=Path(__file__).parent.parent / "static"), name="static")
