"""Risk register API (project-scoped): list, create manually, retrieve, update, delete,
verify, reject, plus a scoring action.

``score`` is derived data written by the risk-scoring service, which is not implemented, so
it stays null; changing probability or impact clears an existing score. Scoring itself
(``POST .../score``) answers 501 until that service exists.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, Risk, RiskCategory, RiskStatus, VerificationStatus
from app.routers._common import (
    NOT_IMPLEMENTED_RESPONSE,
    get_project_or_404,
    http_errors,
    not_implemented,
)
from app.schemas.common import Page
from app.schemas.risk import RiskCreate, RiskRead, RiskUpdate
from app.services import records
from app.services import risks as risk_service

router = APIRouter(prefix="/projects/{project_id}/risks", tags=["risks"])


def _get(db: Session, project: Project, risk_id: int) -> Risk:
    return records.get_owned_or_404(
        db, Risk, risk_id, owner_field="project_id", owner_id=project.id, label="Risk"
    )


@router.post("", response_model=RiskRead, status_code=201, summary="Add a risk")
def create_risk(
    body: RiskCreate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Risk:
    with http_errors():
        return risk_service.create_risk(db, project, body.model_dump(exclude_none=True))


@router.get("", response_model=Page[RiskRead], summary="List a project's risks")
def list_risks(
    category: Optional[RiskCategory] = Query(None),
    status: Optional[RiskStatus] = Query(None),
    verification_status: Optional[VerificationStatus] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Page[RiskRead]:
    conditions = [Risk.project_id == project.id]
    if category is not None:
        conditions.append(Risk.category == category)
    if status is not None:
        conditions.append(Risk.status == status)
    if verification_status is not None:
        conditions.append(Risk.verification_status == verification_status)
    rows, total = records.paginate(db, Risk, conditions, [Risk.code, Risk.id], limit, offset)
    return Page[RiskRead](
        items=[RiskRead.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post(
    "/score",
    summary="Score risks (not available yet)",
    responses=NOT_IMPLEMENTED_RESPONSE,
)
def score_risks(project: Project = Depends(get_project_or_404)) -> None:
    not_implemented("Risk scoring", "the risk-scoring service (app/services/analysis/risk_scoring.py)")


@router.get("/{risk_id}", response_model=RiskRead, summary="Get one risk")
def get_risk(
    risk_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Risk:
    with http_errors():
        return _get(db, project, risk_id)


@router.patch("/{risk_id}", response_model=RiskRead, summary="Update a risk")
def update_risk(
    risk_id: int,
    body: RiskUpdate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Risk:
    with http_errors():
        risk = _get(db, project, risk_id)
        return risk_service.update_risk(db, project, risk, body.model_dump(exclude_unset=True))


@router.post("/{risk_id}/verify", response_model=RiskRead, summary="Mark as Verified")
def verify_risk(
    risk_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Risk:
    with http_errors():
        return risk_service.set_verification(db, _get(db, project, risk_id), VerificationStatus.VERIFIED)


@router.post("/{risk_id}/reject", response_model=RiskRead, summary="Mark as Rejected")
def reject_risk(
    risk_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Risk:
    with http_errors():
        return risk_service.set_verification(db, _get(db, project, risk_id), VerificationStatus.REJECTED)


@router.delete("/{risk_id}", status_code=204, summary="Delete a risk")
def delete_risk(
    risk_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Response:
    with http_errors():
        records.delete_record(db, _get(db, project, risk_id))
    return Response(status_code=204)
