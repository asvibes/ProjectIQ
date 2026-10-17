"""Project resource API (project-scoped): personnel, equipment and subcontractor needs.

A resource may link to one of the project's own company's workforce roles or equipment items
(``company_workforce_role_id`` / ``company_equipment_id``); links to another company's records
are rejected with 422. ``available_quantity`` is whatever a person records; null means
unknown. Gap analysis against company capacity (``GET .../gaps``) answers 501 until the
analysis services exist.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, ProjectResource, ResourceType
from app.routers._common import (
    NOT_IMPLEMENTED_RESPONSE,
    get_project_or_404,
    http_errors,
    not_implemented,
)
from app.schemas.common import Page
from app.schemas.resource import ResourceCreate, ResourceRead, ResourceUpdate
from app.services import records
from app.services import resources as resource_service

router = APIRouter(prefix="/projects/{project_id}/resources", tags=["resources"])


def _get(db: Session, project: Project, resource_id: int) -> ProjectResource:
    return records.get_owned_or_404(
        db, ProjectResource, resource_id, owner_field="project_id", owner_id=project.id, label="Resource"
    )


@router.post("", response_model=ResourceRead, status_code=201, summary="Add a resource need")
def create_resource(
    body: ResourceCreate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> ProjectResource:
    with http_errors():
        return resource_service.create_resource(db, project, body.model_dump(exclude_none=True))


@router.get("", response_model=Page[ResourceRead], summary="List a project's resources")
def list_resources(
    resource_type: Optional[ResourceType] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Page[ResourceRead]:
    conditions = [ProjectResource.project_id == project.id]
    if resource_type is not None:
        conditions.append(ProjectResource.resource_type == resource_type)
    rows, total = records.paginate(
        db, ProjectResource, conditions, [ProjectResource.resource_type, ProjectResource.name, ProjectResource.id],
        limit, offset,
    )
    return Page[ResourceRead](
        items=[ResourceRead.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get(
    "/gaps",
    summary="Resource gap analysis (not available yet)",
    responses=NOT_IMPLEMENTED_RESPONSE,
)
def resource_gaps(project: Project = Depends(get_project_or_404)) -> None:
    not_implemented(
        "Resource gap analysis",
        "the workforce-gap and equipment-options services (app/services/analysis)",
    )


@router.get("/{resource_id}", response_model=ResourceRead, summary="Get one resource")
def get_resource(
    resource_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> ProjectResource:
    with http_errors():
        return _get(db, project, resource_id)


@router.patch("/{resource_id}", response_model=ResourceRead, summary="Update a resource")
def update_resource(
    resource_id: int,
    body: ResourceUpdate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> ProjectResource:
    with http_errors():
        resource = _get(db, project, resource_id)
        return resource_service.update_resource(db, project, resource, body.model_dump(exclude_unset=True))


@router.delete("/{resource_id}", status_code=204, summary="Delete a resource")
def delete_resource(
    resource_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Response:
    with http_errors():
        records.delete_record(db, _get(db, project, resource_id))
    return Response(status_code=204)
