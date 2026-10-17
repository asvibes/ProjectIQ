"""Schemas for project resources (personnel, equipment, subcontractors)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import Field, model_validator

from app.models import ResourceType
from app.models.enums import VerificationStatus
from app.schemas.base import ORMModel, RequestModel
from app.schemas.common import Currency, MoneyIn, Name200


class ResourceCreate(RequestModel):
    resource_type: ResourceType = ResourceType.OTHER
    name: Name200
    required_quantity: int = Field(default=1, ge=0)
    available_quantity: Optional[int] = Field(default=None, ge=0)  # null = unknown
    unit: Optional[str] = Field(default=None, max_length=32)
    unit_cost: Optional[MoneyIn] = None  # null = unknown
    currency: Optional[Currency] = None
    required_from: Optional[date] = None
    required_to: Optional[date] = None
    notes: Optional[str] = None
    company_workforce_role_id: Optional[int] = None
    company_equipment_id: Optional[int] = None
    verification_status: Optional[VerificationStatus] = None

    @model_validator(mode="after")
    def _period_in_order(self) -> "ResourceCreate":
        if self.required_from and self.required_to and self.required_to < self.required_from:
            raise ValueError("required_to cannot be before required_from")
        return self


class ResourceUpdate(RequestModel):
    resource_type: Optional[ResourceType] = None
    name: Optional[Name200] = None
    required_quantity: Optional[int] = Field(default=None, ge=0)
    available_quantity: Optional[int] = Field(default=None, ge=0)
    unit: Optional[str] = Field(default=None, max_length=32)
    unit_cost: Optional[MoneyIn] = None
    currency: Optional[Currency] = None
    required_from: Optional[date] = None
    required_to: Optional[date] = None
    notes: Optional[str] = None
    company_workforce_role_id: Optional[int] = None
    company_equipment_id: Optional[int] = None
    verification_status: Optional[VerificationStatus] = None


class ResourceRead(ORMModel):
    id: int
    project_id: int
    company_workforce_role_id: Optional[int] = None
    company_equipment_id: Optional[int] = None
    resource_type: ResourceType
    name: str
    required_quantity: int
    available_quantity: Optional[int] = None
    unit: Optional[str] = None
    unit_cost: Optional[Decimal] = None
    currency: str
    required_from: Optional[date] = None
    required_to: Optional[date] = None
    notes: Optional[str] = None
    verification_status: VerificationStatus
    last_verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
