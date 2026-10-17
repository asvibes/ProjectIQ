"""Column groups reused across models: timestamps, verification, source references."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.models.enums import VerificationStatus
from app.models.types import UTCDateTime, enum_type, utcnow


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class VerifiableMixin:
    """Verification state. New records are REQUIRES_REVIEW until a person confirms them."""

    verification_status: Mapped[VerificationStatus] = mapped_column(
        enum_type(VerificationStatus),
        default=VerificationStatus.REQUIRES_REVIEW,
        nullable=False,
    )
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)

    def mark_verified(self, when: Optional[datetime] = None) -> None:
        self.verification_status = VerificationStatus.VERIFIED
        self.last_verified_at = when or utcnow()

    def mark_rejected(self) -> None:
        self.verification_status = VerificationStatus.REJECTED


def verified_requires_date() -> CheckConstraint:
    """A record cannot be 'Verified' without a last-verified date."""
    return CheckConstraint(
        "verification_status != 'Verified' OR last_verified_at IS NOT NULL",
        name="verified_has_date",
    )


class SourceLocationMixin:
    """Where in a source document a finding came from, plus the supporting quotation."""

    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Free-form location: "Sheet BOQ!C14", "Section 4.2", "Clause 7(b)"
    location_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    quotation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # None = not checked yet; True/False = result of verification/quote_checker
    quote_verified: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    @validates("page_number")
    def _validate_page_number(self, _key: str, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 1:
            raise ValueError("page_number must be 1 or greater")
        return value


def page_number_positive() -> CheckConstraint:
    return CheckConstraint("page_number IS NULL OR page_number >= 1", name="page_positive")
