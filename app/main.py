"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import init_db
from app.routers import todos


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Database init on startup, cleanup on shutdown."""
    await init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

app.include_router(todos.router, prefix="/api/todos", tags=["todos"])


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "app": settings.app_name}
