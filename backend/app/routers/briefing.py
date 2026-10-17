"""Tender briefing API (project-scoped).

Briefings are stored outputs (``Artifact`` rows of type ``briefing``). Reading the latest
briefing and its earlier versions works against what is stored. Generating one needs the
local AI drafter and the ``briefing_v1`` prompt, both still empty, so ``POST .../generate``
answers 501.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Artifact, ArtifactType, Project
from app.routers._common import (
    NOT_IMPLEMENTED_RESPONSE,
    artifact_read,
    get_project_or_404,
    not_implemented,
)
from app.schemas.artifact import ArtifactRead, BriefingRead
from app.schemas.common import Page
from app.services import records

router = APIRouter(prefix="/projects/{project_id}/briefing", tags=["briefing"])

_BRIEFING = Artifact.artifact_type == ArtifactType.BRIEFING
_NEWEST_FIRST = [Artifact.version.desc(), Artifact.id.desc()]


@router.get("", response_model=BriefingRead, summary="Get the latest stored briefing")
def get_latest_briefing(
    project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)
) -> BriefingRead:
    artifact = db.scalars(
        select(Artifact).where(Artifact.project_id == project.id, _BRIEFING).order_by(*_NEWEST_FIRST).limit(1)
    ).first()
    if artifact is None:
        raise HTTPException(404, f"No briefing has been generated for project {project.id}.")
    return artifact_read(artifact, BriefingRead)


@router.get("/versions", response_model=Page[ArtifactRead], summary="List stored briefing versions")
def list_briefing_versions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Page[ArtifactRead]:
    rows, total = records.paginate(
        db, Artifact, [Artifact.project_id == project.id, _BRIEFING], _NEWEST_FIRST, limit, offset
    )
    return Page[ArtifactRead](
        items=[artifact_read(r, ArtifactRead) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post(
    "/generate",
    summary="Generate a briefing (not available yet)",
    responses=NOT_IMPLEMENTED_RESPONSE,
)
def generate_briefing(project: Project = Depends(get_project_or_404)) -> None:
    not_implemented(
        "Briefing generation",
        "the local AI drafter and its briefing prompt (app/services/ai/drafter.py, prompts/briefing_v1.txt)",
    )
