"""Schemas for the company profile API (company, workforce, equipment, certifications,
past projects)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import AwareDatetime, Field, model_validator

from app.models.enums import EquipmentOwnership, VerificationStatus
from app.schemas.base import ORMModel, RequestModel
from app.schemas.common import Currency, MoneyIn, Name200


# ---------------------------------------------------------------------------- company
class CompanyCreate(RequestModel):
    name: Name200
    legal_name: Optional[str] = Field(default=None, max_length=200)
    industry: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = None
    locations: list[str] = Field(default_factory=list)
    year_founded: Optional[int] = Field(default=None, ge=1000, le=3000)
    objectives: Optional[str] = None
    currency: Optional[Currency] = None
    annual_revenue: Optional[MoneyIn] = None
    working_capital: Optional[MoneyIn] = None
    bank_guarantee_limit: Optional[MoneyIn] = None
    financial_constraints: Optional[str] = None


class CompanyUpdate(RequestModel):
    name: Optional[Name200] = None
    legal_name: Optional[str] = Field(default=None, max_length=200)
    industry: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = None
    locations: Optional[list[str]] = None
    year_founded: Optional[int] = Field(default=None, ge=1000, le=3000)
    objectives: Optional[str] = None
    currency: Optional[Currency] = None
    annual_revenue: Optional[MoneyIn] = None
    working_capital: Optional[MoneyIn] = None
    bank_guarantee_limit: Optional[MoneyIn] = None
    financial_constraints: Optional[str] = None


class CompanyRead(ORMModel):
    id: int
    name: str
    legal_name: Optional[str] = None
    industry: Optional[str] = None
    description: Optional[str] = None
    locations: list[str]
    year_founded: Optional[int] = None
    objectives: Optional[str] = None
    currency: str
    annual_revenue: Optional[Decimal] = None
    working_capital: Optional[Decimal] = None
    bank_guarantee_limit: Optional[Decimal] = None
    financial_constraints: Optional[str] = None
    field_verification: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class FieldVerificationUpdate(RequestModel):
    """Set the verification state of one scalar profile field."""

    status: VerificationStatus
    source_document_id: Optional[int] = None
    last_verified_at: Optional[AwareDatetime] = None


# ----------------------------------------------------------------- shared child fields
class _VerificationIn(RequestModel):
    verification_status: Optional[VerificationStatus] = None  # create default: Requires review
    source_location: Optional[str] = Field(default=None, max_length=255)
    source_document_id: Optional[int] = None


class _VerificationOut(ORMModel):
    verification_status: VerificationStatus
    last_verified_at: Optional[datetime] = None
    source_location: Optional[str] = None
    source_document_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------------- workforce
class WorkforceRoleCreate(_VerificationIn):
    role: Name200
    department: Optional[str] = Field(default=None, max_length=120)
    headcount: int = Field(default=0, ge=0)
    available_headcount: Optional[int] = Field(default=None, ge=0)  # unknown until stated
    skills: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class WorkforceRoleUpdate(_VerificationIn):
    role: Optional[Name200] = None
    department: Optional[str] = Field(default=None, max_length=120)
    headcount: Optional[int] = Field(default=None, ge=0)
    available_headcount: Optional[int] = Field(default=None, ge=0)
    skills: Optional[list[str]] = None
    notes: Optional[str] = None


class WorkforceRoleRead(_VerificationOut):
    id: int
    company_id: int
    role: str
    department: Optional[str] = None
    headcount: int
    available_headcount: Optional[int] = None
    skills: list[str]
    notes: Optional[str] = None


# ------------------------------------------------------------------------- equipment
class EquipmentCreate(_VerificationIn):
    name: Name200
    equipment_type: Optional[str] = Field(default=None, max_length=120)
    quantity: int = Field(default=1, ge=0)
    capacity: Optional[str] = Field(default=None, max_length=255)
    ownership: EquipmentOwnership = EquipmentOwnership.UNKNOWN
    condition_notes: Optional[str] = None


class EquipmentUpdate(_VerificationIn):
    name: Optional[Name200] = None
    equipment_type: Optional[str] = Field(default=None, max_length=120)
    quantity: Optional[int] = Field(default=None, ge=0)
    capacity: Optional[str] = Field(default=None, max_length=255)
    ownership: Optional[EquipmentOwnership] = None
    condition_notes: Optional[str] = None


class EquipmentRead(_VerificationOut):
    id: int
    company_id: int
    name: str
    equipment_type: Optional[str] = None
    quantity: int
    capacity: Optional[str] = None
    ownership: EquipmentOwnership
    condition_notes: Optional[str] = None


# --------------------------------------------------------------------- certifications
class CertificationCreate(_VerificationIn):
    name: Name200
    issuing_body: Optional[str] = Field(default=None, max_length=200)
    certificate_number: Optional[str] = Field(default=None, max_length=120)
    issued_date: Optional[date] = None
    expiry_date: Optional[date] = None

    @model_validator(mode="after")
    def _dates_in_order(self) -> "CertificationCreate":
        if self.issued_date and self.expiry_date and self.expiry_date < self.issued_date:
            raise ValueError("expiry_date cannot be before issued_date")
        return self


class CertificationUpdate(_VerificationIn):
    name: Optional[Name200] = None
    issuing_body: Optional[str] = Field(default=None, max_length=200)
    certificate_number: Optional[str] = Field(default=None, max_length=120)
    issued_date: Optional[date] = None
    expiry_date: Optional[date] = None


class CertificationRead(_VerificationOut):
    id: int
    company_id: int
    name: str
    issuing_body: Optional[str] = None
    certificate_number: Optional[str] = None
    issued_date: Optional[date] = None
    expiry_date: Optional[date] = None


# --------------------------------------------------------------------- past projects
class PastProjectCreate(_VerificationIn):
    title: Name200
    client: Optional[str] = Field(default=None, max_length=200)
    project_type: Optional[str] = Field(default=None, max_length=120)
    location: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    contract_value: Optional[MoneyIn] = None
    currency: Optional[Currency] = None
    start_date: Optional[date] = None
    completion_date: Optional[date] = None

    @model_validator(mode="after")
    def _dates_in_order(self) -> "PastProjectCreate":
        if self.start_date and self.completion_date and self.completion_date < self.start_date:
            raise ValueError("completion_date cannot be before start_date")
        return self


class PastProjectUpdate(_VerificationIn):
    title: Optional[Name200] = None
    client: Optional[str] = Field(default=None, max_length=200)
    project_type: Optional[str] = Field(default=None, max_length=120)
    location: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    contract_value: Optional[MoneyIn] = None
    currency: Optional[Currency] = None
    start_date: Optional[date] = None
    completion_date: Optional[date] = None


class PastProjectRead(_VerificationOut):
    id: int
    company_id: int
    title: str
    client: Optional[str] = None
    project_type: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    contract_value: Optional[Decimal] = None
    currency: str
    start_date: Optional[date] = None
    completion_date: Optional[date] = None
