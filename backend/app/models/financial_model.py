"""Inputs and stored results for the deterministic finance engine (FR-21, FR-22).

``FinancialModel`` holds one project's financial assumptions (bid price, timing, payment
terms and percentage parameters); ``FinancialCostItem`` holds its cost lines. Both are plain
data: cost totals, break-even, bid price and cash flow are calculated by ``services/finance``
and written back to ``FinancialModel.results``. Nothing here is calculated by the ORM.

Conventions: amounts are ``Money`` (NULL = unknown, 0 = zero); percentages are stored as
fractions between 0 and 1 (``0.10`` = 10%) with 4 decimal places.
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship, validates

from app.config import get_settings
from app.database import Base
from app.models.mixins import TimestampMixin, VerifiableMixin, verified_requires_date
from app.models.types import Money, UTCDateTime, enum_type, normalize_currency, normalize_money

# Fractions 0..1 with 4 decimal places (e.g. 0.0750 = 7.5%).
Rate = Numeric(7, 4, asdecimal=True)
# Cost-line quantities (BOQ quantities are often fractional: tonnes, m3, hours).
Quantity = Numeric(14, 3, asdecimal=True)

_MAX_QUANTITY = Decimal("100000000000")  # fits Numeric(14, 3)

RATE_FIELDS = (
    "advance_payment_rate",
    "retention_rate",
    "performance_guarantee_rate",
    "contingency_rate",
    "overhead_rate",
    "target_margin_rate",
)


class CostCategory(str, enum.Enum):
    LABOUR = "labour"
    MATERIALS = "materials"
    EQUIPMENT = "equipment"
    SUBCONTRACTOR = "subcontractor"
    LOGISTICS = "logistics"
    PERMITS_INSURANCE = "permits_insurance"
    SITE_OVERHEAD = "site_overhead"
    OTHER = "other"


class CostBehavior(str, enum.Enum):
    """How a cost moves with volume; needed for break-even. NULL on the row = not classified."""

    FIXED = "fixed"
    VARIABLE = "variable"


def normalize_rate(value: Any, field: str = "rate") -> Optional[Decimal]:
    if value is None:
        return None
    try:
        rate = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not a valid number: {value!r}") from exc
    if not rate.is_finite():
        raise ValueError(f"{field} must be finite")
    if rate < 0 or rate > 1:
        raise ValueError(f"{field} must be a fraction between 0 and 1")
    return rate.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def normalize_quantity(value: Any, field: str = "quantity") -> Optional[Decimal]:
    if value is None:
        return None
    try:
        quantity = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not a valid number: {value!r}") from exc
    if not quantity.is_finite():
        raise ValueError(f"{field} must be finite")
    if quantity < 0:
        raise ValueError(f"{field} cannot be negative")
    if quantity >= _MAX_QUANTITY:
        raise ValueError(f"{field} is too large")
    return quantity.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _rate_check(column: str) -> CheckConstraint:
    return CheckConstraint(
        f"{column} IS NULL OR ({column} >= 0 AND {column} <= 1)", name=f"{column}_fraction"
    )


class FinancialModel(TimestampMixin, Base):
    __tablename__ = "financial_models"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_financial_models_project_name"),
        CheckConstraint("length(currency) = 3", name="currency_iso_length"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("bid_price IS NULL OR bid_price >= 0", name="bid_price_non_negative"),
        CheckConstraint(
            "duration_months IS NULL OR duration_months >= 1", name="duration_positive"
        ),
        CheckConstraint(
            "payment_terms_days IS NULL OR payment_terms_days >= 0",
            name="payment_terms_non_negative",
        ),
        *(_rate_check(name) for name in RATE_FIELDS),
        CheckConstraint("results IS NULL OR calculated_at IS NOT NULL", name="results_have_timestamp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(200), default="Base case", nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(
        String(3), default=lambda: get_settings().default_currency, nullable=False
    )

    # ---- revenue and timing assumptions (NULL = unknown) ------------------------
    bid_price: Mapped[Optional[Decimal]] = mapped_column(Money)
    duration_months: Mapped[Optional[int]] = mapped_column(Integer)
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    payment_terms_days: Mapped[Optional[int]] = mapped_column(Integer)

    # ---- financial parameters, as fractions of the relevant base ----------------
    advance_payment_rate: Mapped[Optional[Decimal]] = mapped_column(Rate)
    retention_rate: Mapped[Optional[Decimal]] = mapped_column(Rate)
    performance_guarantee_rate: Mapped[Optional[Decimal]] = mapped_column(Rate)
    contingency_rate: Mapped[Optional[Decimal]] = mapped_column(Rate)
    overhead_rate: Mapped[Optional[Decimal]] = mapped_column(Rate)
    target_margin_rate: Mapped[Optional[Decimal]] = mapped_column(Rate)

    # Human-readable assumptions behind the inputs, one statement per item.
    assumptions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Calculated output of services/finance; NULL = not calculated yet.
    results: Mapped[Optional[dict]] = mapped_column(JSON(none_as_null=True))
    calculated_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    engine_version: Mapped[Optional[str]] = mapped_column(String(40))

    # The reverse side (``Project.financial_models``) is created here so project.py is untouched.
    project: Mapped["Project"] = relationship(  # noqa: F821
        backref=backref(
            "financial_models",
            cascade="all, delete-orphan",
            passive_deletes=True,
            order_by="FinancialModel.id",
        )
    )
    cost_items: Mapped[list["FinancialCostItem"]] = relationship(
        back_populates="financial_model",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="FinancialCostItem.id",
    )
    # Deleting a model keeps its scenarios (the DB sets their link to NULL).
    scenarios: Mapped[list["Scenario"]] = relationship(  # noqa: F821
        back_populates="financial_model", passive_deletes=True
    )

    @validates("currency")
    def _validate_currency(self, _key: str, value: str) -> str:
        return normalize_currency(value)  # type: ignore[return-value]

    @validates("bid_price")
    def _validate_money(self, key: str, value: Any) -> Optional[Decimal]:
        return normalize_money(value, key)

    @validates(*RATE_FIELDS)
    def _validate_rate(self, key: str, value: Any) -> Optional[Decimal]:
        return normalize_rate(value, key)

    @validates("assumptions")
    def _validate_assumptions(self, _key: str, value: Any) -> list:
        value = [] if value is None else value
        if not isinstance(value, list):
            raise ValueError("assumptions must be a list")
        return value

    @validates("results")
    def _validate_results(self, _key: str, value: Any) -> Optional[dict]:
        if value is not None and not isinstance(value, dict):
            raise ValueError("results must be an object or None")
        return value


class FinancialCostItem(TimestampMixin, VerifiableMixin, Base):
    """One cost line of a financial model (e.g. a BOQ line, a labour allowance)."""

    __tablename__ = "financial_cost_items"
    __table_args__ = (
        CheckConstraint("length(trim(description)) > 0", name="description_not_blank"),
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
        CheckConstraint("unit_cost IS NULL OR unit_cost >= 0", name="unit_cost_non_negative"),
        CheckConstraint("start_month IS NULL OR start_month >= 0", name="start_month_non_negative"),
        CheckConstraint(
            "start_month IS NULL OR end_month IS NULL OR end_month >= start_month",
            name="end_after_start",
        ),
        verified_requires_date(),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    financial_model_id: Mapped[int] = mapped_column(
        ForeignKey("financial_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Provenance: deleting the source document keeps the cost line.
    source_document_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    source_location: Mapped[Optional[str]] = mapped_column(String(255))  # e.g. "Sheet BOQ!C14"

    category: Mapped[CostCategory] = mapped_column(
        enum_type(CostCategory), default=CostCategory.OTHER, nullable=False
    )
    # NULL = not classified as fixed or variable yet.
    cost_behavior: Mapped[Optional[CostBehavior]] = mapped_column(enum_type(CostBehavior))
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("1"), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(32))
    unit_cost: Mapped[Optional[Decimal]] = mapped_column(Money)  # NULL = unknown

    # Month offsets from project start, used for cash-flow timing (0 = first month).
    start_month: Mapped[Optional[int]] = mapped_column(Integer)
    end_month: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    financial_model: Mapped[FinancialModel] = relationship(back_populates="cost_items")
    source_document: Mapped[Optional["Document"]] = relationship()  # noqa: F821

    @validates("unit_cost")
    def _validate_money(self, key: str, value: Any) -> Optional[Decimal]:
        return normalize_money(value, key)

    @validates("quantity")
    def _validate_quantity(self, key: str, value: Any) -> Decimal:
        result = normalize_quantity(value, key)
        if result is None:
            raise ValueError("quantity is required")
        return result