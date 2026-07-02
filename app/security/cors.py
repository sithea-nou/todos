"""Optional CORS configuration derived from settings."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


def add_cors(app: FastAPI) -> None:
    """Add permissive CORS only when ``CORS_ORIGINS`` is configured.

    The same-origin frontend (served at ``/``) needs no CORS headers, so we
    leave CORS disabled by default. Set ``CORS_ORIGINS=*`` or a comma list
    to enable a separate SPA / external client.
    """
    raw = settings.cors_origins.strip()
    if not raw:
        return

    if raw == "*":
        origins = ["*"]
        allow_credentials = False
    else:
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        allow_credentials = True

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
