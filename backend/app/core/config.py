"""Application configuration loaded from environment variables / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_prefix="GTF_",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "GuessTheFrame"
    version: str = "1.0.0"
    env: str = "development"
    host: str = "127.0.0.1"
    port: int = 5274
    frontend_url: str = "http://localhost:5174"

    database_url: str = (
        f"sqlite+aiosqlite:///{(PROJECT_ROOT / 'data' / 'guessTheFrame.db').as_posix()}"
    )

    encryption_key: str = ""
    setup_token: str = ""
    admin_emby_usernames: str = ""

    session_cookie_name: str = "gtf_session"
    session_cookie_secure: bool = False
    session_idle_days: int = 7
    session_absolute_days: int = 30
    csrf_header_name: str = "X-CSRF-Token"

    frame_cache_dir: Path = PROJECT_ROOT / "data" / "frames"
    frame_cache_max_mb: int = 2048
    ffmpeg_path: str = ""
    ffmpeg_timeout_seconds: int = 30
    ffmpeg_concurrency: int = 2

    emby_url: str = "http://192.168.1.50:8096"
    emby_verify_tls: bool = True
    sync_interval_minutes: int = 360

    log_level: str = "INFO"

    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"

    @field_validator("frame_cache_dir", "data_dir", mode="after")
    @classmethod
    def _absolute_path(cls, value: Path) -> Path:
        return value if value.is_absolute() else (PROJECT_ROOT / value).resolve()

    @property
    def is_production(self) -> bool:
        return self.env.lower() in {"production", "prod"}

    @property
    def admin_usernames(self) -> set[str]:
        return {
            name.strip().casefold()
            for name in self.admin_emby_usernames.split(",")
            if name.strip()
        }

    @property
    def secrets_ready(self) -> bool:
        return bool(self.encryption_key) and self.encryption_key != "change-me"

    @property
    def setup_token_ready(self) -> bool:
        return bool(self.setup_token) and self.setup_token != "change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
