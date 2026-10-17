"""Financial model API (project-scoped): assumptions and cost lines.

This router stores and edits *inputs*. The calculations (cost totals, break-even, bid price,
cash flow) belong to ``services/finance``, which is not implemented yet, so
``POST .../calculate`` answers 501 and ``results`` / ``calculated_at`` / ``engine_version``
stay null and are never accepted from clients or modified by this router.

Rates are fractions between 0 and 1 (0.10 = 10%); money is non-negative. A model or cost line
belonging to another project answers 404, like a missing one.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CostCategory, FinancialCostItem, FinancialModel, Project
from app.routers._common import (
    NOT_IMPLEMENTED_RESPONSE,
    get_project_or_404,
    http_errors,
    not_implemented,
)
from app.schemas.common import Page
from app.schemas.financial import (
    CostItemCreate,
    CostItemRead,
    CostItemUpdate,
    FinancialModelCreate,
    FinancialModelRead,
    FinancialModelUpdate,
)
from app.services import financial as financial_service
from app.services import records

router = APIRouter(prefix="/projects/{project_id}/financial-models", tags=["financials"])


def _model_get(db: Session, project: Project, model_id: int) -> FinancialModel:
    return records.get_owned_or_404(
        db, FinancialModel, model_id, owner_field="project_id", owner_id=project.id, label="Financial model"
    )


def _item_get(db: Session, model: FinancialModel, item_id: int) -> FinancialCostItem:
    return records.get_owned_or_404(
        db, FinancialCostItem, item_id, owner_field="financial_model_id", owner_id=model.id, label="Cost item"
    )


def _read(model: FinancialModel) -> FinancialModelRead:
    return FinancialModelRead.model_validate(model)


# ------------------------------------------------------------------------------ models
@router.post("", response_model=FinancialModelRead, status_code=201, summary="Create a financial model")
def create_model(
    body: FinancialModelCreate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> FinancialModelRead:
    with http_errors():
        return _read(financial_service.create_model(db, project, body.model_dump(exclude_none=True)))


@router.get("", response_model=Page[FinancialModelRead], summary="List a project's financial models")
def list_models(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Page[FinancialModelRead]:
    rows, total = records.paginate(
        db, FinancialModel, [FinancialModel.project_id == project.id], [FinancialModel.id], limit, offset
    )
    return Page[FinancialModelRead](items=[_read(r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/{model_id}", response_model=FinancialModelRead, summary="Get one financial model")
def get_model(
    model_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> FinancialModelRead:
    with http_errors():
        return _read(_model_get(db, project, model_id))


@router.patch("/{model_id}", response_model=FinancialModelRead, summary="Update a financial model")
def update_model(
    model_id: int,
    body: FinancialModelUpdate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> FinancialModelRead:
    with http_errors():
        model = _model_get(db, project, model_id)
        return _read(financial_service.update_model(db, model, body.model_dump(exclude_unset=True)))


@router.delete("/{model_id}", status_code=204, summary="Delete a financial model and its cost lines")
def delete_model(
    model_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Response:
    """Scenarios that referenced the model are kept and detached from it."""
    with http_errors():
        records.delete_record(db, _model_get(db, project, model_id))
    return Response(status_code=204)


@router.post(
    "/{model_id}/calculate",
    summary="Run the finance calculations (not available yet)",
    responses=NOT_IMPLEMENTED_RESPONSE,
)
def calculate_model(
    model_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> None:
    with http_errors():
        _model_get(db, project, model_id)  # 404 first for an unknown or foreign model
    not_implemented(
        "Financial calculation",
        "the finance engine (app/services/finance: cost_model, bid_pricing, breakeven, cashflow)",
    )


# -------------------------------------------------------------------------- cost items
@router.post(
    "/{model_id}/cost-items", response_model=CostItemRead, status_code=201, summary="Add a cost line"
)
def create_cost_item(
    model_id: int,
    body: CostItemCreate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> FinancialCostItem:
    with http_errors():
        model = _model_get(db, project, model_id)
        return financial_service.create_item(db, project, model, body.model_dump(exclude_none=True))


@router.get("/{model_id}/cost-items", response_model=Page[CostItemRead], summary="List a model's cost lines")
def list_cost_items(
    model_id: int,
    category: Optional[CostCategory] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Page[CostItemRead]:
    with http_errors():
        model = _model_get(db, project, model_id)
    conditions = [FinancialCostItem.financial_model_id == model.id]
    if category is not None:
        conditions.append(FinancialCostItem.category == category)
    rows, total = records.paginate(db, FinancialCostItem, conditions, [FinancialCostItem.id], limit, offset)
    return Page[CostItemRead](
        items=[CostItemRead.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{model_id}/cost-items/{item_id}", response_model=CostItemRead, summary="Get one cost line")
def get_cost_item(
    model_id: int,
    item_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> FinancialCostItem:
    with http_errors():
        return _item_get(db, _model_get(db, project, model_id), item_id)


@router.patch("/{model_id}/cost-items/{item_id}", response_model=CostItemRead, summary="Update a cost line")
def update_cost_item(
    model_id: int,
    item_id: int,
    body: CostItemUpdate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> FinancialCostItem:
    with http_errors():
        model = _model_get(db, project, model_id)
        item = _item_get(db, model, item_id)
        return financial_service.update_item(db, project, model, item, body.model_dump(exclude_unset=True))


@router.delete("/{model_id}/cost-items/{item_id}", status_code=204, summary="Delete a cost line")
def delete_cost_item(
    model_id: int,
    item_id: int,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> Response:
    with http_errors():
        model = _model_get(db, project, model_id)
        financial_service.delete_item(db, model, _item_get(db, model, item_id))
    return Response(status_code=204)
