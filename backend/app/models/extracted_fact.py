"""A fact pulled out of a source document, always with the quotation that supports it.

Facts start as "Requires review". They are never treated as verified until a person
confirms them (``mark_verified``).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import FactType
from app.models.mixins import (
    SourceLocationMixin,
    TimestampMixin,
    VerifiableMixin,
    page_number_positive,
    verified_requires_date,
)
from app.models.types import enum_type


class ExtractedFact(TimestampMixin, VerifiableMixin, SourceLocationMixin, Base):
    __tablename__ = "extracted_facts"
    __table_args__ = (
        CheckConstraint("length(trim(quotation)) > 0", name="quotation_not_blank"),
        CheckConstraint("length(trim(value)) > 0", name="value_not_blank"),
        page_number_positive(),
        verified_requires_date(),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Facts live and die with their source document. The owning project or company is
    # reached through the document, so there is no second copy to keep consistent.
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    fact_type: Mapped[FactType] = mapped_column(
        enum_type(FactType), default=FactType.OTHER, nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(200), nullable=False)  # e.g. "Submission deadline"
    value: Mapped[str] = mapped_column(Text, nullable=False)  # as written in the source
    normalized_value: Mapped[Optional[str]] = mapped_column(String(255))  # e.g. ISO date, number
    unit: Mapped[Optional[str]] = mapped_column(String(50))

    # Unlike other source references, a supporting quotation is mandatory for facts.
    quotation: Mapped[str] = mapped_column(Text, nullable=False)

    extractor: Mapped[Optional[str]] = mapped_column(String(120))  # prompt/model version

    document: Mapped["Document"] = relationship(back_populates="extracted_facts")  # noqa: F821
