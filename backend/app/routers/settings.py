"""Application settings API (read-only).

Exposes only non-sensitive values. The database URL, storage paths and any credentials are
never returned. Settings come from environment variables (see ``app.config``); there is no
persisted, editable settings store, and no Ollama configuration exists yet, so there is
nothing to update or to report about the AI service.
"""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.engine.url import make_url

from app import __version__
from app.config import get_settings
from app.schemas.settings import SettingsRead

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsRead, summary="Read non-sensitive application settings")
def read_settings() -> SettingsRead:
    settings = get_settings()
    return SettingsRead(
        version=__version__,
        environment=settings.app_env,
        default_currency=settings.default_currency,
        database_backend=make_url(settings.database_url).get_backend_name(),
    )
