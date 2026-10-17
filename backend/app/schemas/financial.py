"""Schemas for financial models and their cost lines."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import Field, model_validator

from app.models import CostBehavior, CostCategory
from app.models.enums import VerificationStatus
from app.schemas.base import ORMModel, RequestModel
from app.schemas.common import Currency, MoneyIn, Name200, RateIn, Text255

QuantityIn = Field(ge=0, lt=Decimal("100000000000"))


class FinancialModelCreate(RequestModel):
    name: Name200 = "Base case"
    description: Optional[str] = None
    currency: Optional[Currency] = None
    bid_price: Optional[MoneyIn] = None
    duration_months: Optional[int] = Field(default=None, ge=1)
    start_date: Optional[date] = None
    payment_terms_days: Optional[int] = Field(default=None, ge=0)
    advance_payment_rate: Optional[RateIn] = None
    retention_rate: Optional[RateIn] = None
    performance_guarantee_rate: Optional[RateIn] = None
    contingency_rate: Optional[RateIn] = None
    overhead_rate: Optional[RateIn] = None
    target_margin_rate: Optional[RateIn] = None
    assumptions: list[str] = Field(default_factory=list)


class FinancialModelUpdate(RequestModel):
    name: Optional[Name200] = None
    description: Optional[str] = None
    currency: Optional[Currency] = None
    bid_price: Optional[MoneyIn] = None
    duration_months: Optional[int] = Field(default=None, ge=1)
    start_date: Optional[date] = None
    payment_terms_days: Optional[int] = Field(default=None, ge=0)
    advance_payment_rate: Optional[RateIn] = None
    retention_rate: Optional[RateIn] = None
    performance_guarantee_rate: Optional[RateIn] = None
    contingency_rate: Optional[RateIn] = None
    overhead_rate: Optional[RateIn] = None
    target_margin_rate: Optional[RateIn] = None
    assumptions: Optional[list[str]] = None


class FinancialModelRead(ORMModel):
    id: int
    project_id: int
    name: str
    description: Optional[str] = None
    currency: str
    bid_price: Optional[Decimal] = None
    duration_months: Optional[int] = None
    start_date: Optional[date] = None
    payment_terms_days: Optional[int] = None
    advance_payment_rate: Optional[Decimal] = None
    retention_rate: Optional[Decimal] = None
    performance_guarantee_rate: Optional[Decimal] = None
    contingency_rate: Optional[Decimal] = None
    overhead_rate: Optional[Decimal] = None
    target_margin_rate: Optional[Decimal] = None
    assumptions: list[str]
    results: Optional[dict[str, Any]] = None  # written by the finance engine only
    calculated_at: Optional[datetime] = None
    engine_version: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CostItemCreate(RequestModel):
    category: CostCategory = CostCategory.OTHER
    cost_behavior: Optional[CostBehavior] = None  # null = not classified
    description: Text255
    quantity: Decimal = Field(default=Decimal("1"), ge=0, lt=Decimal("100000000000"))
    unit: Optional[str] = Field(default=None, max_length=32)
    unit_cost: Optional[MoneyIn] = None  # null = unknown
    start_month: Optional[int] = Field(default=None, ge=0)
    end_month: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = None
    source_document_id: Optional[int] = None
    source_location: Optional[str] = Field(default=None, max_length=255)
    verification_status: Optional[VerificationStatus] = None

    @model_validator(mode="after")
    def _months_in_order(self) -> "CostItemCreate":
        if self.start_month is not None and self.end_month is not None and self.end_month < self.start_month:
            raise ValueError("end_month cannot be before start_month")
        return self


class CostItemUpdate(RequestModel):
    category: Optional[CostCategory] = None
    cost_behavior: Optional[CostBehavior] = None
    description: Optional[Text255] = None
    quantity: Optional[Decimal] = Field(default=None, ge=0, lt=Decimal("100000000000"))
    unit: Optional[str] = Field(default=None, max_length=32)
    unit_cost: Optional[MoneyIn] = None
    start_month: Optional[int] = Field(default=None, ge=0)
    end_month: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = None
    source_document_id: Optional[int] = None
    source_location: Optional[str] = Field(default=None, max_length=255)
    verification_status: Optional[VerificationStatus] = None


class CostItemRead(ORMModel):
    id: int
    financial_model_id: int
    source_document_id: Optional[int] = None
    source_location: Optional[str] = None
    category: CostCategory
    cost_behavior: Optional[CostBehavior] = None
    description: str
    quantity: Decimal
    unit: Optional[str] = None
    unit_cost: Optional[Decimal] = None
    start_month: Optional[int] = None
    end_month: Optional[int] = None
    notes: Optional[str] = None
    verification_status: VerificationStatus
    last_verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
