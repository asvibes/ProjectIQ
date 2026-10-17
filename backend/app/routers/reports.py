"""Generated outputs API (project-scoped): list, inspect and download stored outputs.

Outputs are ``Artifact`` rows (briefings, registers, summaries) held either as a stored file
or as inline text. Generating new reports needs the DOCX/PPTX/CSV builders, which are empty
placeholders, so ``POST .../generate`` answers 501. The stored file location is never
exposed; downloads are served only from inside the storage folder.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Artifact, ArtifactFormat, ArtifactType, Project
from app.routers._common import (
    NOT_IMPLEMENTED_RESPONSE,
    artifact_read,
    get_project_or_404,
    get_storage_dir,
    http_errors,
    not_implemented,
)
from app.schemas.artifact import ArtifactRead, ReportGenerateRequest
from app.schemas.common import Page
from app.services import records
from app.services import reports as report_service

router = APIRouter(prefix="/projects/{project_id}/reports", tags=["reports"])

_INLINE_MEDIA_TYPES = {
    ArtifactFormat.MARKDOWN: ("text/markdown", ".md"),
    ArtifactFormat.JSON: ("application/json", ".json"),
    ArtifactFormat.CSV: ("text/csv", ".csv"),
}


def _get(db: Session, project: Project, artifact_id: int) -> Artifact:
    return records.get_owned_or_404(
        db, Artifact, artifact_id, owner_field="project_id", owner_id=project.id, label="Report"
    )


def _download_name(title: str, suffix: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("._") or "report"
    return f"{stem[:100]}{suffix}"


@router.get("", response_model=Page[ArtifactRead], summary="List a project's generated outputs")
def list_reports(
    artifact_type: Optional[ArtifactType] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Page[ArtifactRead]:
    conditions = [Artifact.project_id == project.id]
    if artifact_type is not None:
        conditions.append(Artifact.artifact_type == artifact_type)
    rows, total = records.paginate(db, Artifact, conditions, [Artifact.id.desc()], limit, offset)
    return Page[ArtifactRead](
        items=[artifact_read(r, ArtifactRead) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post(
    "/generate",
    summary="Generate a report (not available yet)",
    responses=NOT_IMPLEMENTED_RESPONSE,
)
def generate_report(body: ReportGenerateRequest, project: Project = Depends(get_project_or_404)) -> None:
    not_implemented(
        "Report generation",
        "the export builders (app/services/export: docx_builder, pptx_builder, csv_export)",
    )


@router.get("/{artifact_id}", response_model=ArtifactRead, summary="Get one output's details")
def get_report(
    artifact_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> ArtifactRead:
    with http_errors():
        return artifact_read(_get(db, project, artifact_id), ArtifactRead)


@router.get("/{artifact_id}/download", summary="Download an output")
def download_report(
    artifact_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    storage_dir: Path = Depends(get_storage_dir),
):
    with http_errors():
        artifact = _get(db, project, artifact_id)
        if artifact.storage_path:
            path = report_service.artifact_file(storage_dir, artifact)
            return FileResponse(
                path,
                media_type=artifact.mime_type or "application/octet-stream",
                filename=_download_name(artifact.title, path.suffix),
            )
    # Inline text output (no stored file).
    media_type, suffix = _INLINE_MEDIA_TYPES.get(artifact.file_format, ("text/plain", ".txt"))
    return Response(
        content=artifact.content or "",
        media_type=f"{media_type}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{_download_name(artifact.title, suffix)}"'},
    )
