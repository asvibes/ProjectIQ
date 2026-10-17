"""Schemas for the settings API. Only non-sensitive values are exposed."""
from __future__ import annotations

from app.schemas.base import ORMModel


class SettingsRead(ORMModel):
    version: str
    environment: str
    default_currency: str
    database_backend: str
