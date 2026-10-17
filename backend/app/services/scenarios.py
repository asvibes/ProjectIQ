"""Rules for scenarios (inputs only). ``results`` are written by the finance engine, which is
not implemented, so the API never accepts them."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.models import FinancialModel, Project, Scenario
from app.services import records
from app.services.errors import ServiceError

NON_NULLABLE = ("name", "kind", "assumptions", "overrides", "extra")
CONFLICT = "This project already has a scenario with that name, or already has a baseline scenario."


def _require_model_in_project(db: Session, project: Project, model_id: Any) -> None:
    if model_id is None:
        return
    model = db.get(FinancialModel, model_id)
    if model is None or model.project_id != project.id:
        raise ServiceError(422, f"Financial model {model_id} does not belong to this project.")


def create_scenario(db: Session, project: Project, values: Mapping[str, Any]) -> Scenario:
    _require_model_in_project(db, project, values.get("financial_model_id"))
    values = dict(values, project_id=project.id)
    return records.create_record(db, Scenario, values, conflict_message=CONFLICT)


def update_scenario(db: Session, project: Project, scenario: Scenario, values: Mapping[str, Any]) -> Scenario:
    _require_model_in_project(db, project, values.get("financial_model_id"))
    return records.update_record(
        db, scenario, values, non_nullable=NON_NULLABLE, conflict_message=CONFLICT
    )
