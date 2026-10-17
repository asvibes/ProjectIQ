"""Scenario API (project-scoped): alternative prices, schedules and assumptions.

Scenarios store *inputs* (``assumptions``, ``overrides``). Their ``results`` are written by
the finance engine (``services/finance``, not implemented), so ``POST .../calculate`` answers
501 and results stay null; clients cannot set them.

``GET .../compare`` is read-only: it lays the *stored* results of 2-10 scenarios side by side.
It never recalculates, and scenarios without results are reported as not calculated.

A project has at most one ``baseline`` scenario and scenario names are unique per project
(409 otherwise). A scenario or financial model of another project answers 404 / 422.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, Scenario, ScenarioKind
from app.routers._common import (
    NOT_IMPLEMENTED_RESPONSE,
    get_project_or_404,
    http_errors,
    not_implemented,
)
from app.schemas.common import Page
from app.schemas.scenario import ScenarioComparison, ScenarioCreate, ScenarioRead, ScenarioUpdate
from app.services import records
from app.services import scenario_compare
from app.services import scenarios as scenario_service

router = APIRouter(prefix="/projects/{project_id}/scenarios", tags=["scenarios"])


def _get(db: Session, project: Project, scenario_id: int) -> Scenario:
    return records.get_owned_or_404(
        db, Scenario, scenario_id, owner_field="project_id", owner_id=project.id, label="Scenario"
    )


def _read(scenario: Scenario) -> ScenarioRead:
    return ScenarioRead.model_validate(scenario)


@router.post("", response_model=ScenarioRead, status_code=201, summary="Create a scenario")
def create_scenario(
    body: ScenarioCreate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> ScenarioRead:
    with http_errors():
        return _read(scenario_service.create_scenario(db, project, body.model_dump(exclude_none=True)))


@router.get("", response_model=Page[ScenarioRead], summary="List a project's scenarios")
def list_scenarios(
    kind: Optional[ScenarioKind] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Page[ScenarioRead]:
    conditions = [Scenario.project_id == project.id]
    if kind is not None:
        conditions.append(Scenario.kind == kind)
    rows, total = records.paginate(db, Scenario, conditions, [Scenario.id], limit, offset)
    return Page[ScenarioRead](items=[_read(r) for r in rows], total=total, limit=limit, offset=offset)


@router.get(
    "/compare",
    response_model=ScenarioComparison,
    summary="Compare stored scenario results side by side",
)
def compare_scenarios(
    ids: list[int] = Query(..., description="Scenario ids to compare (2-10), e.g. ?ids=1&ids=2"),
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> dict:
    with http_errors():
        return scenario_compare.compare_stored(db, project.id, ids)


@router.get("/{scenario_id}", response_model=ScenarioRead, summary="Get one scenario")
def get_scenario(
    scenario_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> ScenarioRead:
    with http_errors():
        return _read(_get(db, project, scenario_id))


@router.patch("/{scenario_id}", response_model=ScenarioRead, summary="Update a scenario")
def update_scenario(
    scenario_id: int,
    body: ScenarioUpdate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> ScenarioRead:
    with http_errors():
        scenario = _get(db, project, scenario_id)
        return _read(
            scenario_service.update_scenario(db, project, scenario, body.model_dump(exclude_unset=True))
        )


@router.delete("/{scenario_id}", status_code=204, summary="Delete a scenario")
def delete_scenario(
    scenario_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Response:
    with http_errors():
        records.delete_record(db, _get(db, project, scenario_id))
    return Response(status_code=204)


@router.post(
    "/{scenario_id}/calculate",
    summary="Calculate a scenario (not available yet)",
    responses=NOT_IMPLEMENTED_RESPONSE,
)
def calculate_scenario(
    scenario_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> None:
    with http_errors():
        _get(db, project, scenario_id)
    not_implemented("Scenario calculation", "the finance engine (app/services/finance/scenarios.py)")
