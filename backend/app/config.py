"""Application settings, read from environment variables and an optional .env file.

Every value has a safe local-first default, so the backend runs with no .env at all.
Relative paths are resolved against ``backend/`` so behaviour does not depend on the
directory the process was started from.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

_SQLITE_PREFIX = "sqlite:///"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Later files win, so backend/.env overrides the repo-root .env.
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    storage_dir: Path = Field(default=BACKEND_DIR / "storage")
    database_url: Optional[str] = None
    sql_echo: bool = False
    default_currency: str = "USD"

    # Local Ollama server used by app/services/ai. Documents never leave this machine unless
    # OLLAMA_BASE_URL is deliberately pointed elsewhere (the client logs a warning if so).
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:4b"
    ollama_timeout_seconds: float = Field(default=120.0, gt=0, le=1800)

    @field_validator("ollama_base_url")
    @classmethod
    def _ollama_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.lower().startswith(("http://", "https://")):
            raise ValueError("OLLAMA_BASE_URL must start with http:// or https://")
        return value

    @field_validator("ollama_model")
    @classmethod
    def _ollama_model_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("OLLAMA_MODEL cannot be blank")
        return value

    @field_validator("default_currency")
    @classmethod
    def _currency_code(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("DEFAULT_CURRENCY must be a 3-letter ISO 4217 code")
        return value

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        if not self.storage_dir.is_absolute():
            self.storage_dir = (BACKEND_DIR / self.storage_dir).resolve()

        if not self.database_url:
            self.database_url = f"{_SQLITE_PREFIX}{(self.storage_dir / 'projectiq.db').as_posix()}"
        elif self.database_url.startswith(_SQLITE_PREFIX):
            raw = self.database_url[len(_SQLITE_PREFIX):]
            # "sqlite:///:memory:" and "sqlite://" are in-memory; leave them alone.
            if raw and raw != ":memory:" and not Path(raw).is_absolute():
                self.database_url = f"{_SQLITE_PREFIX}{(BACKEND_DIR / raw).resolve().as_posix()}"
        return self

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def generated_dir(self) -> Path:
        return self.storage_dir / "generated"

    def ensure_storage_dirs(self) -> None:
        """Create storage folders (and the SQLite file's parent folder) if missing."""
        for path in (self.storage_dir, self.uploads_dir, self.generated_dir):
            path.mkdir(parents=True, exist_ok=True)
        if self.database_url and self.database_url.startswith(_SQLITE_PREFIX):
            raw = self.database_url[len(_SQLITE_PREFIX):]
            if raw and raw != ":memory:":
                Path(raw).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
