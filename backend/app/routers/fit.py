"""Company-project fit API (project-scoped).

``GET .../summary`` counts the requirement states already stored for the project (match and
verification status). It performs no matching and produces no score or recommendation; the
response says so. Running the automated matcher (``POST .../run``) answers 501 because
``services/analysis/requirement_matcher`` is an empty placeholder.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project
from app.routers._common import NOT_IMPLEMENTED_RESPONSE, get_project_or_404, not_implemented
from app.schemas.fit import FitRunRequest, FitSummary
from app.services import fit_summary

router = APIRouter(prefix="/projects/{project_id}/fit", tags=["fit"])


@router.get("/summary", response_model=FitSummary, summary="Summary of stored requirement states")
def get_fit_summary(
    project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)
) -> dict:
    return fit_summary.summarise(db, project)


@router.post("/run", summary="Run automated matching (not available yet)", responses=NOT_IMPLEMENTED_RESPONSE)
def run_fit(body: Optional[FitRunRequest] = None, project: Project = Depends(get_project_or_404)) -> None:
    not_implemented(
        "Automated requirement matching",
        "the requirement matcher and gap detector (app/services/analysis)",
    )
