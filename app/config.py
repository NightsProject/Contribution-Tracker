from functools import lru_cache

from pydantic import Field, PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Contrib"
    postgres_db: str = "contribution_tracker"
    postgres_user: str = "contribution"
    postgres_password: str = "change-me-for-local-development"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    uploads_dir: str = "uploads"
    timezone: str = "Asia/Manila"
    session_cookie_secure: bool = False
    session_max_age_seconds: int = Field(default=28800, gt=0, le=2592000)
    max_upload_size_bytes: int = Field(default=5 * 1024 * 1024, gt=0, le=25 * 1024 * 1024)
    web_port: int = 8000
    app_domain: str = "tracker.example.com"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="allow")

    @computed_field
    @property
    def database_url(self) -> str:
        return str(
            PostgresDsn.build(
                scheme="postgresql+psycopg",
                username=self.postgres_user,
                password=self.postgres_password,
                host=self.postgres_host,
                port=self.postgres_port,
                path=f"/{self.postgres_db}",
            )
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
