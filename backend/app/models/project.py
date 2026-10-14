"""A potential project or tender the company is assessing."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.config import get_settings
from app.database import Base
from app.models.enums import ProjectStatus
from app.models.mixins import TimestampMixin
from app.models.types import Money, UTCDateTime, enum_type, normalize_currency, normalize_money


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("length(currency) = 3", name="currency_iso_length"),
        CheckConstraint("budget IS NULL OR budget >= 0", name="budget_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(120))
    client: Mapped[Optional[str]] = mapped_column(String(200))
    location: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    objectives: Mapped[Optional[str]] = mapped_column(Text)
    deliverables: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    constraints: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # One currency per project. Budget is Unknown (NULL) until stated.
    currency: Mapped[str] = mapped_column(
        String(3), default=lambda: get_settings().default_currency, nullable=False
    )
    budget: Mapped[Optional[Decimal]] = mapped_column(Money)
    deadline: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)

    status: Mapped[ProjectStatus] = mapped_column(
        enum_type(ProjectStatus), default=ProjectStatus.DRAFT, nullable=False, index=True
    )

    company: Mapped["Company"] = relationship(back_populates="projects")  # noqa: F821
    documents: Mapped[list["Document"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    requirements: Mapped[list["Requirement"]] = relationship(  # noqa: F821
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Requirement.code",
    )

    @validates("currency")
    def _validate_currency(self, _key: str, value: str) -> str:
        return normalize_currency(value)  # type: ignore[return-value]

    @validates("budget")
    def _validate_budget(self, key: str, value: Any) -> Optional[Decimal]:
        return normalize_money(value, key)
