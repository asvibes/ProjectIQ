"""Scenario comparison (FR-24): alternative prices, schedules or assumptions for a project.

A scenario is stored as *inputs* (``assumptions`` for people, ``overrides`` for the finance
engine) plus the *results* the engine produced from them, so a result can be reproduced from
what is stored (NFR "Determinism"). The model performs no calculation: ``results`` is written
by ``services/finance/scenarios``. ``results`` is NULL until the scenario has been calculated.

Each project has at most one ``baseline`` scenario (enforced by a partial unique index).
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship, validates

from app.database import Base
from app.models.mixins import TimestampMixin
from app.models.types import UTCDateTime, enum_type


class ScenarioKind(str, enum.Enum):
    BASELINE = "baseline"
    PRICE = "price"
    SCHEDULE = "schedule"
    ASSUMPTIONS = "assumptions"
    COMBINED = "combined"


class Scenario(TimestampMixin, Base):
    __tablename__ = "scenarios"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_scenarios_project_name"),
        # One baseline per project. Partial indexes are supported by SQLite and PostgreSQL.
        Index(
            "uq_scenarios_project_baseline",
            "project_id",
            unique=True,
            sqlite_where=text("kind = 'baseline'"),
            postgresql_where=text("kind = 'baseline'"),
        ),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("results IS NULL OR calculated_at IS NOT NULL", name="results_have_timestamp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The financial model whose inputs ``overrides`` are applied to. If that model is
    # deleted the scenario and its stored results survive, detached (NULL).
    financial_model_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("financial_models.id", ondelete="SET NULL"), index=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    kind: Mapped[ScenarioKind] = mapped_column(
        enum_type(ScenarioKind), default=ScenarioKind.ASSUMPTIONS, nullable=False, index=True
    )

    # Human-readable assumptions, one statement per item.
    assumptions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # Machine-readable input changes relative to the base financial model,
    # e.g. {"bid_price": "1250000.00", "duration_months": 14}.
    overrides: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Calculated output of the finance engine; NULL = not calculated yet.
    results: Mapped[Optional[dict]] = mapped_column(JSON(none_as_null=True))
    calculated_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    engine_version: Mapped[Optional[str]] = mapped_column(String(40))

    # Free-form metadata (tags, who/what proposed the scenario, UI hints). No secrets.
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # The reverse side (``Project.scenarios``) is created here so project.py stays untouched.
    project: Mapped["Project"] = relationship(  # noqa: F821
        backref=backref(
            "scenarios",
            cascade="all, delete-orphan",
            passive_deletes=True,
            order_by="Scenario.id",
        )
    )
    financial_model: Mapped[Optional["FinancialModel"]] = relationship(  # noqa: F821
        back_populates="scenarios"
    )

    @validates("assumptions")
    def _validate_assumptions(self, _key: str, value: Any) -> list:
        value = [] if value is None else value
        if not isinstance(value, list):
            raise ValueError("assumptions must be a list")
        return value

    @validates("overrides", "extra")
    def _validate_object(self, key: str, value: Any) -> dict:
        value = {} if value is None else value
        if not isinstance(value, dict):
            raise ValueError(f"{key} must be an object")
        return value

    @validates("results")
    def _validate_results(self, _key: str, value: Any) -> Optional[dict]:
        if value is not None and not isinstance(value, dict):
            raise ValueError("results must be an object or None")
        return value