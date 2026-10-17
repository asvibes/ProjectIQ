"""Schemas for the project chat API."""
from __future__ import annotations

from pydantic import Field

from app.schemas.base import RequestModel


class ChatRequest(RequestModel):
    message: str = Field(min_length=1, max_length=4000)
