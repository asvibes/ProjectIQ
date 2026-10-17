"""Project risk register (FR-23).

A risk is either surfaced from a tender clause (``origin=extracted``, with a source
reference and quotation, see the ``extract_risks`` prompt) or entered by a person
(``origin=manual``). Probability and impact are 1-5 ratings; ``score`` is *stored* here but
calculated by ``services/analysis/risk_scoring`` - the model holds no scoring logic.
NULL probability, impact or score means "not assessed yet", never zero.
"""
from __future__ import annotations

import enum
from typing import Any, Optional

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship, validates

from app.database import Base
from app.models.enums import RequirementOrigin
from app.models.mixins import (
    SourceLocationMixin,
    TimestampMixin,
    VerifiableMixin,
    page_number_positive,
    verified_requires_date,
)
from app.models.types import enum_type

RATING_MIN = 1
RATING_MAX = 5
SCORE_MAX = RATING_MAX * RATING_MAX


class RiskCategory(str, enum.Enum):
    COMMERCIAL = "commercial"
    FINANCIAL = "financial"
    CONTRACTUAL = "contractual"
    TECHNICAL = "technical"
    SCHEDULE = "schedule"
    SAFETY_ENVIRONMENT = "safety_environment"
    REGULATORY = "regulatory"
    RESOURCE = "resource"
    SUPPLY_CHAIN = "supply_chain"
    OTHER = "other"


class RiskStatus(str, enum.Enum):
    IDENTIFIED = "identified"
    ASSESSED = "assessed"
    MITIGATING = "mitigating"
    ACCEPTED = "accepted"
    CLOSED = "closed"


def _check_int_range(key: str, value: Any, low: int, high: int) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be a whole number")
    if not low <= value <= high:
        raise ValueError(f"{key} must be between {low} and {high}")
    return value


class Risk(TimestampMixin, VerifiableMixin, SourceLocationMixin, Base):
    __tablename__ = "risks"
    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_risks_project_code"),
        CheckConstraint(
            f"probability IS NULL OR (probability >= {RATING_MIN} AND probability <= {RATING_MAX})",
            name="probability_range",
        ),
        CheckConstraint(
            f"impact IS NULL OR (impact >= {RATING_MIN} AND impact <= {RATING_MAX})",
            name="impact_range",
        ),
        CheckConstraint(
            f"score IS NULL OR (score >= {RATING_MIN} AND score <= {SCORE_MAX})",
            name="score_range",
        ),
        CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
        page_number_positive(),
        verified_requires_date(),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Deleting the source document keeps the risk and its quotation.
    source_document_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )

    code: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g. "RISK-001"
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[RiskCategory] = mapped_column(
        enum_type(RiskCategory), default=RiskCategory.OTHER, nullable=False, index=True
    )
    status: Mapped[RiskStatus] = mapped_column(
        enum_type(RiskStatus), default=RiskStatus.IDENTIFIED, nullable=False, index=True
    )

    probability: Mapped[Optional[int]] = mapped_column(Integer)  # 1 (rare) .. 5 (almost certain)
    impact: Mapped[Optional[int]] = mapped_column(Integer)  # 1 (negligible) .. 5 (severe)
    score: Mapped[Optional[int]] = mapped_column(Integer)  # written by risk_scoring, 1..25

    mitigation: Mapped[Optional[str]] = mapped_column(Text)
    # A role or team (e.g. "Commercial manager"), not an individual's personal data.
    owner: Mapped[Optional[str]] = mapped_column(String(120))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    origin: Mapped[RequirementOrigin] = mapped_column(
        enum_type(RequirementOrigin), default=RequirementOrigin.MANUAL, nullable=False
    )
    extractor: Mapped[Optional[str]] = mapped_column(String(120))  # e.g. "extract_risks_v1"

    # The reverse side (``Project.risks``) is created here so project.py stays untouched.
    project: Mapped["Project"] = relationship(  # noqa: F821
        backref=backref(
            "risks",
            cascade="all, delete-orphan",
            passive_deletes=True,
            order_by="Risk.code",
        )
    )
    source_document: Mapped[Optional["Document"]] = relationship()  # noqa: F821

    @validates("probability", "impact")
    def _validate_rating(self, key: str, value: Any) -> Optional[int]:
        return _check_int_range(key, value, RATING_MIN, RATING_MAX)

    @validates("score")
    def _validate_score(self, key: str, value: Any) -> Optional[int]:
        return _check_int_range(key, value, RATING_MIN, SCORE_MAX)