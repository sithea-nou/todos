"""Application configuration using pydantic-settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """App settings loaded from environment / .env file."""

    app_name: str = "MyToDo"
    debug: bool = False
    debug_logging: bool = False
    database_url: str = "sqlite+aiosqlite:///./todos.db"
    secret_key: str = "change-me-in-production"

    # Authentication (optional). When api_key is set, non-browser requests
    # must send `Authorization: Bearer <api_key>` or `X-API-Key: <api_key>`.
    # Empty string disables auth (open access — the default for local dev).
    api_key: str = ""

    # CORS (optional). Comma-separated list of allowed origins, or "*" for any.
    # Empty means same-origin only (the frontend served at / is always allowed).
    cors_origins: str = ""

    # Rate limiting on the chat endpoints (requests per minute per client).
    # 0 disables rate limiting.
    chat_rate_limit: int = 0

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ollama_api_key: str = ""
    chat_model: str = "claude-sonnet-4-6"
    chat_api_base: str = ""  # override base URL for local LLMs (e.g. http://localhost:11434/v1)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
