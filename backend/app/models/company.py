"""Contractor company profile and its child records (workforce, equipment, certifications,
past projects).

Every profile fact carries a verification status and a last-verified date. Child rows
carry them as columns; scalar fields on ``Company`` itself are tracked in the
``field_verification`` JSON map (see ``Company.set_field_verification``).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship, validates

from app.config import get_settings
from app.database import Base
from app.models.enums import EquipmentOwnership, VerificationStatus
from app.models.mixins import TimestampMixin, VerifiableMixin, verified_requires_date
from app.models.types import Money, enum_type, normalize_currency, normalize_money, utcnow

# Scalar Company fields that can carry their own verification status.
PROFILE_FIELDS = (
    "name",
    "legal_name",
    "industry",
    "description",
    "locations",
    "year_founded",
    "objectives",
    "currency",
    "annual_revenue",
    "working_capital",
    "bank_guarantee_limit",
    "financial_constraints",
)


class ProfileFactMixin(VerifiableMixin):
    """Verification + provenance for rows that make up the company profile."""

    source_location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    @declared_attr
    def source_document_id(cls) -> Mapped[Optional[int]]:  # noqa: N805
        return mapped_column(
            ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
        )


class Company(TimestampMixin, Base):
    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint("length(currency) = 3", name="currency_iso_length"),
        CheckConstraint("annual_revenue IS NULL OR annual_revenue >= 0", name="revenue_non_negative"),
        CheckConstraint("working_capital IS NULL OR working_capital >= 0", name="capital_non_negative"),
        CheckConstraint(
            "bank_guarantee_limit IS NULL OR bank_guarantee_limit >= 0", name="guarantee_non_negative"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[Optional[str]] = mapped_column(String(200))
    industry: Mapped[Optional[str]] = mapped_column(String(120))
    description: Mapped[Optional[str]] = mapped_column(Text)
    locations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    year_founded: Mapped[Optional[int]] = mapped_column(Integer)
    objectives: Mapped[Optional[str]] = mapped_column(Text)

    # Finances. One currency per company; amounts are Unknown (NULL) until provided.
    currency: Mapped[str] = mapped_column(
        String(3), default=lambda: get_settings().default_currency, nullable=False
    )
    annual_revenue: Mapped[Optional[Decimal]] = mapped_column(Money)
    working_capital: Mapped[Optional[Decimal]] = mapped_column(Money)
    bank_guarantee_limit: Mapped[Optional[Decimal]] = mapped_column(Money)
    financial_constraints: Mapped[Optional[str]] = mapped_column(Text)

    # {"annual_revenue": {"status": "Estimated", "last_verified_at": "...", "source_document_id": 3}}
    field_verification: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    workforce_roles: Mapped[list["CompanyWorkforceRole"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", passive_deletes=True
    )
    equipment: Mapped[list["CompanyEquipment"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", passive_deletes=True
    )
    certifications: Mapped[list["CompanyCertification"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", passive_deletes=True
    )
    past_projects: Mapped[list["CompanyPastProject"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", passive_deletes=True
    )
    projects: Mapped[list["Project"]] = relationship(  # noqa: F821
        back_populates="company", cascade="all, delete-orphan", passive_deletes=True
    )
    documents: Mapped[list["Document"]] = relationship(  # noqa: F821
        back_populates="company", cascade="all, delete-orphan", passive_deletes=True
    )

    # ---- validation -------------------------------------------------------------
    @validates("currency")
    def _validate_currency(self, _key: str, value: str) -> str:
        return normalize_currency(value)  # type: ignore[return-value]

    @validates("annual_revenue", "working_capital", "bank_guarantee_limit")
    def _validate_money(self, key: str, value: Any) -> Optional[Decimal]:
        return normalize_money(value, key)

    @validates("field_verification")
    def _validate_field_verification(self, _key: str, value: Optional[dict]) -> dict:
        value = value or {}
        valid_status = {s.value for s in VerificationStatus}
        for field, entry in value.items():
            if field not in PROFILE_FIELDS:
                raise ValueError(f"Unknown profile field: {field!r}")
            if not isinstance(entry, dict) or entry.get("status") not in valid_status:
                raise ValueError(f"Invalid verification entry for {field!r}")
        return value

    # ---- verification helpers ---------------------------------------------------
    def set_field_verification(
        self,
        field: str,
        status: VerificationStatus,
        *,
        last_verified_at: Optional[datetime] = None,
        source_document_id: Optional[int] = None,
    ) -> None:
        """Record the verification state of one scalar profile field."""
        when = last_verified_at
        if status is VerificationStatus.VERIFIED and when is None:
            when = utcnow()
        updated = dict(self.field_verification or {})  # reassign so the change is tracked
        updated[field] = {
            "status": VerificationStatus(status).value,
            "last_verified_at": when.isoformat() if when else None,
            "source_document_id": source_document_id,
        }
        self.field_verification = updated

    def get_field_status(self, field: str) -> VerificationStatus:
        """Recorded status, else MISSING for an empty field, else REQUIRES_REVIEW."""
        entry = (self.field_verification or {}).get(field)
        if entry:
            return VerificationStatus(entry["status"])
        current = getattr(self, field, None)
        return VerificationStatus.MISSING if current in (None, "", []) else VerificationStatus.REQUIRES_REVIEW


class CompanyWorkforceRole(TimestampMixin, ProfileFactMixin, Base):
    """Role-level workforce capacity. No individual employees are stored."""

    __tablename__ = "company_workforce_roles"
    __table_args__ = (
        UniqueConstraint("company_id", "department", "role", name="uq_workforce_company_dept_role"),
        CheckConstraint("headcount >= 0", name="headcount_non_negative"),
        CheckConstraint(
            "available_headcount IS NULL OR "
            "(available_headcount >= 0 AND available_headcount <= headcount)",
            name="available_within_headcount",
        ),
        verified_requires_date(),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    department: Mapped[Optional[str]] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(120), nullable=False)
    headcount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Employed does not mean available. NULL = availability is Unknown.
    available_headcount: Mapped[Optional[int]] = mapped_column(Integer)
    skills: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    company: Mapped[Company] = relationship(back_populates="workforce_roles")


class CompanyEquipment(TimestampMixin, ProfileFactMixin, Base):
    __tablename__ = "company_equipment"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
        verified_requires_date(),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    equipment_type: Mapped[Optional[str]] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    capacity: Mapped[Optional[str]] = mapped_column(String(255))
    ownership: Mapped[EquipmentOwnership] = mapped_column(
        enum_type(EquipmentOwnership), default=EquipmentOwnership.UNKNOWN, nullable=False
    )
    condition_notes: Mapped[Optional[str]] = mapped_column(Text)

    company: Mapped[Company] = relationship(back_populates="equipment")


class CompanyCertification(TimestampMixin, ProfileFactMixin, Base):
    __tablename__ = "company_certifications"
    __table_args__ = (
        CheckConstraint(
            "issued_date IS NULL OR expiry_date IS NULL OR expiry_date >= issued_date",
            name="expiry_after_issue",
        ),
        verified_requires_date(),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    issuing_body: Mapped[Optional[str]] = mapped_column(String(200))
    certificate_number: Mapped[Optional[str]] = mapped_column(String(120))
    issued_date: Mapped[Optional[date]] = mapped_column(Date)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date)

    company: Mapped[Company] = relationship(back_populates="certifications")


class CompanyPastProject(TimestampMixin, ProfileFactMixin, Base):
    __tablename__ = "company_past_projects"
    __table_args__ = (
        CheckConstraint("length(currency) = 3", name="currency_iso_length"),
        CheckConstraint("contract_value IS NULL OR contract_value >= 0", name="value_non_negative"),
        CheckConstraint(
            "start_date IS NULL OR completion_date IS NULL OR completion_date >= start_date",
            name="completion_after_start",
        ),
        verified_requires_date(),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    client: Mapped[Optional[str]] = mapped_column(String(200))
    project_type: Mapped[Optional[str]] = mapped_column(String(120))
    location: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    contract_value: Mapped[Optional[Decimal]] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(
        String(3), default=lambda: get_settings().default_currency, nullable=False
    )
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    completion_date: Mapped[Optional[date]] = mapped_column(Date)

    company: Mapped[Company] = relationship(back_populates="past_projects")

    @validates("currency")
    def _validate_currency(self, _key: str, value: str) -> str:
        return normalize_currency(value)  # type: ignore[return-value]

    @validates("contract_value")
    def _validate_value(self, key: str, value: Any) -> Optional[Decimal]:
        return normalize_money(value, key)
