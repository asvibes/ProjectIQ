"""Requirements extracted from tender documents (or added manually).

Two independent state fields:
  * ``match_status``        - how the company compares (defaults to Unknown).
  * ``verification_status`` - whether a person has reviewed the requirement itself.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import MatchStatus, RequirementCategory, RequirementOrigin
from app.models.mixins import (
    SourceLocationMixin,
    TimestampMixin,
    VerifiableMixin,
    page_number_positive,
    verified_requires_date,
)
from app.models.types import UTCDateTime, enum_type


class Requirement(TimestampMixin, VerifiableMixin, SourceLocationMixin, Base):
    __tablename__ = "requirements"
    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_requirements_project_code"),
        page_number_positive(),
        verified_requires_date(),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Source document is optional: manual requirements have none, and deleting a
    # document keeps the requirement and its quotation.
    source_document_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )

    code: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g. "REQ-001"
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[RequirementCategory] = mapped_column(
        enum_type(RequirementCategory), default=RequirementCategory.OTHER, nullable=False
    )
    # NULL means the source does not say whether it is mandatory (stays Unknown).
    is_mandatory: Mapped[Optional[bool]] = mapped_column()
    deadline: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)

    match_status: Mapped[MatchStatus] = mapped_column(
        enum_type(MatchStatus), default=MatchStatus.UNKNOWN, nullable=False, index=True
    )
    evidence_summary: Mapped[Optional[str]] = mapped_column(Text)  # evidence used
    missing_evidence: Mapped[Optional[str]] = mapped_column(Text)  # evidence that would close the gap

    origin: Mapped[RequirementOrigin] = mapped_column(
        enum_type(RequirementOrigin), default=RequirementOrigin.EXTRACTED, nullable=False
    )
    extractor: Mapped[Optional[str]] = mapped_column(String(120))  # e.g. "extract_requirements_v1"
    assigned_role: Mapped[Optional[str]] = mapped_column(String(120))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    project: Mapped["Project"] = relationship(back_populates="requirements")  # noqa: F821
    source_document: Mapped[Optional["Document"]] = relationship(  # noqa: F821
        back_populates="requirements"
    )
