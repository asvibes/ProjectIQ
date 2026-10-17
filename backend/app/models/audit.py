"""Append-only audit trail of changes and decisions (FR-27).

One row records who did what to which record and when. Rows are never edited: the ORM
refuses to update or delete an ``AuditLog`` (bulk Core statements and direct SQL are not
intercepted, so a retention job must use those deliberately).

Audit rows must outlive what they describe, so ``project_id`` / ``company_id`` are
``ON DELETE SET NULL`` and the target is a plain ``(target_type, target_id, target_label)``
snapshot rather than a foreign key. Record *what changed* in ``changes``
(``{"field": {"old": ..., "new": ...}}``); do not store secrets, prompts, model responses or
raw document text there.

There is no user-account system yet (FR-30), so ``actor`` is a free-text label such as
``"local-user"``, ``"system"`` or an AI task name.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, String, event
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.database import Base
from app.models.types import UTCDateTime, enum_type, utcnow


class AuditActorType(str, enum.Enum):
    USER = "user"
    SYSTEM = "system"
    AI = "ai"


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint("length(trim(actor)) > 0", name="actor_not_blank"),
        CheckConstraint("length(trim(action)) > 0", name="action_not_blank"),
        CheckConstraint("target_id IS NULL OR target_type IS NOT NULL", name="target_id_needs_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Only a creation time: audit rows are immutable, so there is no updated_at.
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False, index=True
    )

    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )

    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_type: Mapped[AuditActorType] = mapped_column(
        enum_type(AuditActorType), default=AuditActorType.USER, nullable=False
    )
    # Dotted verb, e.g. "requirement.verified", "document.deleted", "project.status_changed".
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    target_type: Mapped[Optional[str]] = mapped_column(String(64))  # e.g. "requirement"
    target_id: Mapped[Optional[int]] = mapped_column(Integer)
    target_label: Mapped[Optional[str]] = mapped_column(String(255))  # name/code at the time

    changes: Mapped[Optional[dict]] = mapped_column(JSON(none_as_null=True))
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    @validates("actor", "action")
    def _validate_required_text(self, key: str, value: Optional[str]) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError(f"{key} is required")
        return value

    @validates("changes")
    def _validate_changes(self, _key: str, value: Any) -> Optional[dict]:
        if value is not None and not isinstance(value, dict):
            raise ValueError("changes must be an object or None")
        return value

    @validates("extra")
    def _validate_extra(self, _key: str, value: Any) -> dict:
        value = {} if value is None else value
        if not isinstance(value, dict):
            raise ValueError("extra must be an object")
        return value


@event.listens_for(AuditLog, "before_update")
def _audit_rows_are_immutable(_mapper, _connection, _target) -> None:  # noqa: ANN001
    raise ValueError("Audit log rows are append-only and cannot be modified")


@event.listens_for(AuditLog, "before_delete")
def _audit_rows_are_permanent(_mapper, _connection, _target) -> None:  # noqa: ANN001
    raise ValueError("Audit log rows are append-only and cannot be deleted")