"""Tender requirement API (project-scoped): list, create manually, retrieve, update, delete,
verify, reject.

Requirements extracted from documents arrive as "Requires review"; a person confirms or
rejects them here. ``match_status`` defaults to "Unknown" and is only changed by an explicit
request. ``quote_verified`` is written by the quote checker and cannot be set through this API.
A record belonging to a different project answers 404, exactly like a missing one.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    MatchStatus,
    Project,
    Requirement,
    RequirementCategory,
    VerificationStatus,
)
from app.routers._common import get_project_or_404, http_errors
from app.schemas.common import Page
from app.schemas.requirement import RequirementCreate, RequirementRead, RequirementUpdate
from app.services import records
from app.services import requirements as requirement_service

router = APIRouter(prefix="/projects/{project_id}/requirements", tags=["requirements"])


def _get(db: Session, project: Project, requirement_id: int) -> Requirement:
    return records.get_owned_or_404(
        db, Requirement, requirement_id, owner_field="project_id", owner_id=project.id, label="Requirement"
    )


@router.post("", response_model=RequirementRead, status_code=201, summary="Add a requirement manually")
def create_requirement(
    body: RequirementCreate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Requirement:
    with http_errors():
        return requirement_service.create_requirement(db, project, body.model_dump(exclude_none=True))


@router.get("", response_model=Page[RequirementRead], summary="List a project's requirements")
def list_requirements(
    category: Optional[RequirementCategory] = Query(None),
    match_status: Optional[MatchStatus] = Query(None),
    verification_status: Optional[VerificationStatus] = Query(None),
    is_mandatory: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Page[RequirementRead]:
    conditions = [Requirement.project_id == project.id]
    if category is not None:
        conditions.append(Requirement.category == category)
    if match_status is not None:
        conditions.append(Requirement.match_status == match_status)
    if verification_status is not None:
        conditions.append(Requirement.verification_status == verification_status)
    if is_mandatory is not None:
        conditions.append(Requirement.is_mandatory == is_mandatory)
    rows, total = records.paginate(db, Requirement, conditions, [Requirement.code, Requirement.id], limit, offset)
    return Page[RequirementRead](
        items=[RequirementRead.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{requirement_id}", response_model=RequirementRead, summary="Get one requirement")
def get_requirement(
    requirement_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Requirement:
    with http_errors():
        return _get(db, project, requirement_id)


@router.patch("/{requirement_id}", response_model=RequirementRead, summary="Update a requirement")
def update_requirement(
    requirement_id: int,
    body: RequirementUpdate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Requirement:
    with http_errors():
        requirement = _get(db, project, requirement_id)
        return requirement_service.update_requirement(
            db, project, requirement, body.model_dump(exclude_unset=True)
        )


@router.post("/{requirement_id}/verify", response_model=RequirementRead, summary="Mark as Verified")
def verify_requirement(
    requirement_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Requirement:
    with http_errors():
        requirement = _get(db, project, requirement_id)
        return requirement_service.set_verification(db, requirement, VerificationStatus.VERIFIED)


@router.post("/{requirement_id}/reject", response_model=RequirementRead, summary="Mark as Rejected")
def reject_requirement(
    requirement_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Requirement:
    with http_errors():
        requirement = _get(db, project, requirement_id)
        return requirement_service.set_verification(db, requirement, VerificationStatus.REJECTED)


@router.delete("/{requirement_id}", status_code=204, summary="Delete a requirement")
def delete_requirement(
    requirement_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Response:
    with http_errors():
        records.delete_record(db, _get(db, project, requirement_id))
    return Response(status_code=204)
