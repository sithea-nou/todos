"""Application configuration using pydantic-settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """App settings loaded from environment / .env file."""

    app_name: str = "MyToDo"
    debug: bool = False
    database_url: str = "sqlite+aiosqlite:///./todos.db"
    secret_key: str = "change-me-in-production"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
