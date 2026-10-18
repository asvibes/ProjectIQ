"""Rules for financial models and cost lines (inputs only).

Calculations belong to ``services/finance``. ``calculate_model`` below is the only writer of
``results``, ``calculated_at`` and ``engine_version``; the API never accepts those fields from
clients. Editing inputs does not clear stored results: ``results["provenance"]`` carries a
fingerprint of the inputs used, so a stale result can be detected by recalculating.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.models import FinancialCostItem, FinancialModel, Project
from app.models.types import utcnow
from app.services import records
from app.services.errors import ServiceError
from app.services.finance.cashflow import calculate_financial_results
from app.services.finance.cost_model import ENGINE_VERSION, FinanceInputError, inputs_from_model
from app.services.finance.scenarios import inputs_fingerprint

MODEL_NON_NULLABLE = ("name", "currency", "assumptions")
ITEM_NON_NULLABLE = ("category", "description", "quantity")
NAME_CONFLICT = "A financial model with this name already exists in the project."


def create_model(db: Session, project: Project, values: Mapping[str, Any]) -> FinancialModel:
    values = dict(values, project_id=project.id)
    return records.create_record(db, FinancialModel, values, conflict_message=NAME_CONFLICT)


def update_model(db: Session, model: FinancialModel, values: Mapping[str, Any]) -> FinancialModel:
    return records.update_record(
        db, model, values, non_nullable=MODEL_NON_NULLABLE, conflict_message=NAME_CONFLICT
    )


def _check_months(item: FinancialCostItem) -> None:
    if item.start_month is not None and item.end_month is not None and item.end_month < item.start_month:
        raise ServiceError(422, "end_month cannot be before start_month.")


def create_item(
    db: Session, project: Project, model: FinancialModel, values: Mapping[str, Any]
) -> FinancialCostItem:
    values = dict(values)
    verification = values.pop("verification_status", None)
    records.require_document_owned(db, values.get("source_document_id"), project_id=project.id)
    item = FinancialCostItem(financial_model_id=model.id)
    records.apply_values(item, values)
    if verification is not None:
        records.apply_verification(item, verification)
    _check_months(item)
    db.add(item)
    records.commit(db)
    return item


def update_item(
    db: Session, project: Project, model: FinancialModel, item: FinancialCostItem, values: Mapping[str, Any]
) -> FinancialCostItem:
    values = dict(values)
    verification = None
    if "verification_status" in values:
        verification = values.pop("verification_status")
        if verification is None:
            raise ServiceError(422, "verification_status cannot be null.")
    records.require_document_owned(db, values.get("source_document_id"), project_id=project.id)
    records.apply_values(item, values, non_nullable=ITEM_NON_NULLABLE)
    if verification is not None:
        records.apply_verification(item, verification)
    _check_months(item)
    records.commit(db)
    return item


def delete_item(db: Session, model: FinancialModel, item: FinancialCostItem) -> None:
    db.delete(item)
    records.commit(db)


def calculate_model(db: Session, model: FinancialModel) -> FinancialModel:
    """Run the deterministic finance engine on the stored inputs and store the results.

    Missing inputs are not an error: the engine reports them in the results (``None`` values
    and status fields) instead of assuming zeros. Only inconsistent stored data (which the
    API and ORM already prevent) raises 422.
    """
    try:
        inputs = inputs_from_model(model)
        results = calculate_financial_results(inputs)
    except FinanceInputError as exc:
        raise ServiceError(422, f"The financial model's inputs are invalid: {exc}") from exc
    results["provenance"] = {
        "engine_version": ENGINE_VERSION,
        "inputs_fingerprint": inputs_fingerprint(inputs),
    }
    model.results = results
    model.calculated_at = utcnow()
    model.engine_version = ENGINE_VERSION
    records.commit(db)
    return model
