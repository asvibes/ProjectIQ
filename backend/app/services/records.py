"""Generic record helpers shared by the API's CRUD endpoints.

Everything here is persistence-level rules (ownership checks, unique codes, safe commits,
verification transitions). Nothing in this module calculates anything.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Optional, TypeVar

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Document, VerificationStatus
from app.services.errors import ServiceError

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# committing
# ---------------------------------------------------------------------------
def commit(db: Session, *, conflict_message: str = "A record with the same unique value already exists.") -> None:
    """Commit, translating database constraint failures into ``ServiceError``.

    The raw database message is logged, never returned: it can contain table and column names.
    """
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Integrity error on commit: %s", exc.orig)
        text = str(exc.orig).lower()
        if "unique" in text:
            raise ServiceError(409, conflict_message) from exc
        if "foreign key" in text:
            raise ServiceError(422, "A referenced record does not exist.") from exc
        raise ServiceError(422, "The values violate a data constraint.") from exc


def flush(db: Session, *, conflict_message: str = "A record with the same unique value already exists.") -> None:
    """Flush with the same error translation as ``commit`` (used to obtain generated ids)."""
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Integrity error on flush: %s", exc.orig)
        text = str(exc.orig).lower()
        if "unique" in text:
            raise ServiceError(409, conflict_message) from exc
        if "foreign key" in text:
            raise ServiceError(422, "A referenced record does not exist.") from exc
        raise ServiceError(422, "The values violate a data constraint.") from exc


# ---------------------------------------------------------------------------
# lookup and ownership
# ---------------------------------------------------------------------------
def get_or_404(db: Session, model: type[T], record_id: int, label: str) -> T:
    record = db.get(model, record_id)
    if record is None:
        raise ServiceError(404, f"{label} {record_id} not found.")
    return record


def get_owned_or_404(
    db: Session, model: type[T], record_id: int, *, owner_field: str, owner_id: int, label: str
) -> T:
    """Fetch a record that must belong to ``owner_id``.

    A record that exists under a different owner gets the same 404 as a missing one, so the
    API never confirms that an id exists in an unrelated project or company.
    """
    record = db.get(model, record_id)
    if record is None or getattr(record, owner_field) != owner_id:
        raise ServiceError(404, f"{label} {record_id} not found.")
    return record


def require_document_owned(
    db: Session,
    document_id: Optional[int],
    *,
    project_id: Optional[int] = None,
    company_id: Optional[int] = None,
) -> None:
    """A provenance link must point at a document of the same project (or company)."""
    if document_id is None:
        return
    document = db.get(Document, document_id)
    ok = document is not None and (
        (project_id is not None and document.project_id == project_id)
        or (company_id is not None and document.company_id == company_id)
    )
    if not ok:
        raise ServiceError(422, f"Source document {document_id} does not belong to this record's owner.")


# ---------------------------------------------------------------------------
# listing
# ---------------------------------------------------------------------------
def paginate(
    db: Session,
    model: type[T],
    conditions: Sequence[Any],
    order_by: Iterable[Any],
    limit: int,
    offset: int,
) -> tuple[list[T], int]:
    total = db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0
    rows = db.scalars(
        select(model).where(*conditions).order_by(*order_by).limit(limit).offset(offset)
    ).all()
    return list(rows), total


# ---------------------------------------------------------------------------
# applying input
# ---------------------------------------------------------------------------
def apply_values(
    record: Any, values: Mapping[str, Any], *, non_nullable: Iterable[str] = ()
) -> None:
    """Set attributes from validated request data.

    The ORM models validate their own fields (money, rates, ratings...) and raise
    ``ValueError`` with a user-presentable message; that becomes a 422 here.
    """
    blocked = set(non_nullable)
    for key, value in values.items():
        if value is None and key in blocked:
            raise ServiceError(422, f"{key} cannot be null.")
        try:
            setattr(record, key, value)
        except ValueError as exc:
            raise ServiceError(422, str(exc)) from exc


def apply_verification(record: Any, status: VerificationStatus) -> None:
    """Move a verifiable record to ``status``.

    ``Verified`` stamps ``last_verified_at`` (the database refuses Verified without it). Any
    other status keeps an earlier date, which is meaningful history for e.g. ``Outdated``.
    """
    if status is VerificationStatus.VERIFIED:
        record.mark_verified()
    else:
        record.verification_status = status


# ---------------------------------------------------------------------------
# codes such as REQ-001 / RISK-001
# ---------------------------------------------------------------------------
def next_code(db: Session, model: Any, project_id: int, prefix: str) -> str:
    """Next free ``<prefix>-NNN`` code within a project (max existing number + 1)."""
    codes = db.scalars(select(model.code).where(model.project_id == project_id)).all()
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    highest = 0
    for code in codes:
        match = pattern.match(code)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:03d}"


# ---------------------------------------------------------------------------
# generic create / update / delete
# ---------------------------------------------------------------------------
def create_record(
    db: Session,
    model: type[T],
    values: Mapping[str, Any],
    *,
    conflict_message: str = "A record with the same unique value already exists.",
) -> T:
    record = model()
    apply_values(record, values)
    db.add(record)
    commit(db, conflict_message=conflict_message)
    return record


def update_record(
    db: Session,
    record: T,
    values: Mapping[str, Any],
    *,
    non_nullable: Iterable[str] = (),
    conflict_message: str = "A record with the same unique value already exists.",
) -> T:
    apply_values(record, values, non_nullable=non_nullable)
    commit(db, conflict_message=conflict_message)
    return record


def delete_record(db: Session, record: Any) -> None:
    db.delete(record)
    commit(db)
