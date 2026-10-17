"""Helpers shared by the routers. The leading underscore keeps this module out of router
discovery (see ``app.routers``)."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NoReturn

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Project
from app.services.errors import ServiceError


@contextmanager
def http_errors() -> Iterator[None]:
    """Translate service-layer errors into ``{"detail": ...}`` HTTP errors."""
    try:
        yield
    except ServiceError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


def not_implemented(feature: str, blocked_by: str) -> NoReturn:
    """501 for actions whose backing service is still an empty placeholder."""
    raise HTTPException(
        status_code=501,
        detail=f"{feature} is not available yet: {blocked_by} is not implemented.",
    )


NOT_IMPLEMENTED_RESPONSE = {501: {"description": "The backing service is not implemented yet."}}


def get_storage_dir() -> Path:
    """Dependency so tests can point generated-file storage at a temporary directory."""
    return get_settings().storage_dir


def get_project_or_404(project_id: int, db: Session = Depends(get_db)) -> Project:
    """Resolve the ``{project_id}`` path parameter of project-scoped routes."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found.")
    return project


def artifact_read(artifact, schema):
    """Build an artifact response, filling the two flags that are not columns.

    ``storage_path`` is deliberately never part of the response schemas."""
    out = schema.model_validate(artifact)
    out.has_file = artifact.storage_path is not None
    out.has_content = artifact.content is not None
    return out
