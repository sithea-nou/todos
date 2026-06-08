"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastmcp.utilities.lifespan import combine_lifespans

from app.config import settings
from app.database import init_db
from app.mcp_server import mcp
from app.routers import todos


@asynccontextmanager
async def app_lifespan(app: FastAPI):
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
app.mount("/mcp", mcp_app)


@app.get("/")
async def serve_frontend():
    """Serve the frontend HTML."""
    html_path = Path(__file__).parent.parent / "index.html"
    return HTMLResponse(content=html_path.read_text())


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "app": settings.app_name}
