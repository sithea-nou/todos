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
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    chat_model: str = "claude-sonnet-4-6"
    chat_api_base: str = ""  # override base URL for local LLMs (e.g. http://localhost:11434/v1)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
