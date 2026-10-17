"""Schemas for generated outputs (briefings and reports). ``storage_path`` is never exposed."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import Field

from app.models import ArtifactFormat, ArtifactType
from app.schemas.base import ORMModel, RequestModel


class ArtifactRead(ORMModel):
    id: int
    project_id: int
    artifact_type: ArtifactType
    file_format: ArtifactFormat
    title: str
    description: Optional[str] = None
    mime_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    sha256: Optional[str] = None
    version: int
    generated_by: Optional[str] = None
    extra: dict[str, Any]
    has_file: bool = False  # not a column: filled in by the router
    has_content: bool = False  # not a column: filled in by the router
    created_at: datetime
    updated_at: datetime


class BriefingRead(ArtifactRead):
    content: Optional[str] = None


class ReportGenerateRequest(RequestModel):
    artifact_type: ArtifactType
    file_format: ArtifactFormat
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
