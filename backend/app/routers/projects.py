"""Project API: create, list, retrieve, update, delete.

A project belongs to exactly one company (``company_id`` is required on creation and cannot
be changed). Errors use FastAPI's ``{"detail": "..."}`` shape: 404 unknown company/project,
422 invalid values. Deleting a project also deletes everything it owns (documents and their
stored files, requirements, risks, resources, financial models, scenarios, outputs).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, ProjectStatus
from app.routers._common import get_project_or_404, get_storage_dir, http_errors
from app.routers.documents import get_upload_dir
from app.schemas.common import Page
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services import projects as project_service
from app.services import records

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=201, summary="Create a project")
def create_project(body: ProjectCreate, db: Session = Depends(get_db)) -> Project:
    with http_errors():
        return project_service.create_project(db, body.model_dump(exclude_none=True))


@router.get("", response_model=Page[ProjectRead], summary="List projects")
def list_projects(
    company_id: Optional[int] = Query(None),
    status: Optional[ProjectStatus] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page[ProjectRead]:
    conditions = []
    if company_id is not None:
        conditions.append(Project.company_id == company_id)
    if status is not None:
        conditions.append(Project.status == status)
    rows, total = records.paginate(db, Project, conditions, [Project.id.desc()], limit, offset)
    return Page[ProjectRead](
        items=[ProjectRead.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{project_id}", response_model=ProjectRead, summary="Get one project")
def get_project(project: Project = Depends(get_project_or_404)) -> Project:
    return project


@router.patch("/{project_id}", response_model=ProjectRead, summary="Update a project")
def update_project(
    body: ProjectUpdate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Project:
    with http_errors():
        return project_service.update_project(db, project, body.model_dump(exclude_unset=True))


@router.delete("/{project_id}", status_code=204, summary="Delete a project and everything it owns")
def delete_project(
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    uploads_dir: Path = Depends(get_upload_dir),
    storage_dir: Path = Depends(get_storage_dir),
) -> Response:
    with http_errors():
        project_service.delete_project(db, project, uploads_dir=uploads_dir, storage_dir=storage_dir)
    return Response(status_code=204)
