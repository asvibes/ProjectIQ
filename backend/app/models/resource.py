"""Resources a project needs (personnel, equipment, subcontractors), with quantities, cost and
the company capacity they are expected to come from.

A resource row is the project-side *requirement*. Company capacity lives in
``CompanyWorkforceRole`` / ``CompanyEquipment``; the optional links below say which company
record a resource is drawn from. Comparing the two (gap analysis) is done in
``services/analysis``, not here. Role-level data only: no individual people are stored.
NULL availability or cost means unknown; zero means zero.
"""
from __future__ import annotations

import enum
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship, validates

from app.config import get_settings
from app.database import Base
from app.models.mixins import TimestampMixin, VerifiableMixin, verified_requires_date
from app.models.types import Money, enum_type, normalize_currency, normalize_money


class ResourceType(str, enum.Enum):
    PERSONNEL = "personnel"
    EQUIPMENT = "equipment"
    SUBCONTRACTOR = "subcontractor"
    OTHER = "other"


class ProjectResource(TimestampMixin, VerifiableMixin, Base):
    __tablename__ = "project_resources"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(currency) = 3", name="currency_iso_length"),
        CheckConstraint("required_quantity >= 0", name="required_non_negative"),
        CheckConstraint(
            "available_quantity IS NULL OR available_quantity >= 0", name="available_non_negative"
        ),
        CheckConstraint("unit_cost IS NULL OR unit_cost >= 0", name="unit_cost_non_negative"),
        CheckConstraint(
            "required_from IS NULL OR required_to IS NULL OR required_to >= required_from",
            name="period_order",
        ),
        # A resource draws on at most one company record, and of the matching kind.
        CheckConstraint(
            "company_workforce_role_id IS NULL OR company_equipment_id IS NULL",
            name="single_company_link",
        ),
        CheckConstraint(
            "company_workforce_role_id IS NULL OR resource_type = 'personnel'",
            name="workforce_link_is_personnel",
        ),
        CheckConstraint(
            "company_equipment_id IS NULL OR resource_type = 'equipment'",
            name="equipment_link_is_equipment",
        ),
        verified_requires_date(),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Deleting the company record keeps the project's resource need; the link becomes NULL.
    company_workforce_role_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("company_workforce_roles.id", ondelete="SET NULL"), index=True
    )
    company_equipment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("company_equipment.id", ondelete="SET NULL"), index=True
    )

    resource_type: Mapped[ResourceType] = mapped_column(
        enum_type(ResourceType), default=ResourceType.OTHER, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)  # role or equipment name
    required_quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # How many the company can actually provide; NULL = unknown.
    available_quantity: Mapped[Optional[int]] = mapped_column(Integer)

    unit: Mapped[Optional[str]] = mapped_column(String(32))  # what unit_cost is per, e.g. "month"
    unit_cost: Mapped[Optional[Decimal]] = mapped_column(Money)  # NULL = unknown
    currency: Mapped[str] = mapped_column(
        String(3), default=lambda: get_settings().default_currency, nullable=False
    )

    required_from: Mapped[Optional[date]] = mapped_column(Date)
    required_to: Mapped[Optional[date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # The reverse side (``Project.resources``) is created here so project.py stays untouched.
    project: Mapped["Project"] = relationship(  # noqa: F821
        backref=backref(
            "resources",
            cascade="all, delete-orphan",
            passive_deletes=True,
            order_by="ProjectResource.id",
        )
    )
    company_workforce_role: Mapped[Optional["CompanyWorkforceRole"]] = relationship()  # noqa: F821
    company_equipment: Mapped[Optional["CompanyEquipment"]] = relationship()  # noqa: F821

    @validates("currency")
    def _validate_currency(self, _key: str, value: str) -> str:
        return normalize_currency(value)  # type: ignore[return-value]

    @validates("unit_cost")
    def _validate_money(self, key: str, value: Any) -> Optional[Decimal]:
        return normalize_money(value, key)

    @validates("required_quantity", "available_quantity")
    def _validate_quantity(self, key: str, value: Any) -> Optional[int]:
        if value is None:
            if key == "required_quantity":
                raise ValueError("required_quantity is required")
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{key} must be a whole number")
        if value < 0:
            raise ValueError(f"{key} cannot be negative")
        return value