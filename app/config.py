from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Contribution & Expense Tracker"
    database_url: str = (
        "postgresql+psycopg://contribution:"
        "change-me-for-local-development@localhost:5432/contribution_tracker"
    )
    uploads_dir: str = "uploads"
    timezone: str = "Asia/Manila"
    session_cookie_secure: bool = False
    session_max_age_seconds: int = Field(default=28800, gt=0, le=2592000)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
