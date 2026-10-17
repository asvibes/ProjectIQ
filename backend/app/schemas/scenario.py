"""Schemas for scenarios and their comparison."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import Field

from app.models import ScenarioKind
from app.schemas.base import ORMModel, RequestModel
from app.schemas.common import Name200


class ScenarioCreate(RequestModel):
    name: Name200
    description: Optional[str] = None
    kind: ScenarioKind = ScenarioKind.ASSUMPTIONS
    financial_model_id: Optional[int] = None
    assumptions: list[str] = Field(default_factory=list)
    overrides: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class ScenarioUpdate(RequestModel):
    name: Optional[Name200] = None
    description: Optional[str] = None
    kind: Optional[ScenarioKind] = None
    financial_model_id: Optional[int] = None
    assumptions: Optional[list[str]] = None
    overrides: Optional[dict[str, Any]] = None
    extra: Optional[dict[str, Any]] = None


class ScenarioRead(ORMModel):
    id: int
    project_id: int
    financial_model_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    kind: ScenarioKind
    assumptions: list[str]
    overrides: dict[str, Any]
    results: Optional[dict[str, Any]] = None  # written by the finance engine only
    calculated_at: Optional[datetime] = None
    engine_version: Optional[str] = None
    extra: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ScenarioComparisonEntry(ORMModel):
    id: int
    name: str
    kind: ScenarioKind
    calculated: bool
    calculated_at: Optional[datetime] = None
    results: Optional[dict[str, Any]] = None


class ScenarioComparison(ORMModel):
    """Stored results side by side. Nothing is recalculated.

    ``metrics`` maps each top-level scalar key found in any scenario's stored results to the
    value per scenario id (null where a scenario has no such value or is not calculated).
    """

    project_id: int
    scenarios: list[ScenarioComparisonEntry]
    metrics: dict[str, dict[int, Any]]
    not_calculated: list[int]
