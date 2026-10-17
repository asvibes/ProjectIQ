"""Company profile rules: verification bookkeeping, child records, cascade file cleanup."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import (
    Company,
    CompanyCertification,
    CompanyEquipment,
    CompanyPastProject,
    CompanyWorkforceRole,
    VerificationStatus,
)
from app.models.company import PROFILE_FIELDS
from app.services import files, records
from app.services.errors import ServiceError

COMPANY_NON_NULLABLE = ("name", "currency", "locations")


# ---------------------------------------------------------------------------
# company
# ---------------------------------------------------------------------------
def create_company(db: Session, values: Mapping[str, Any]) -> Company:
    return records.create_record(db, Company, values)


def update_company(db: Session, company: Company, values: Mapping[str, Any]) -> Company:
    """Apply a partial update.

    If a profile field that was marked Verified gets a different value, its verification is
    reset to "Requires review": the earlier verification applied to the old value.
    """
    before = {key: getattr(company, key) for key in values if key in PROFILE_FIELDS}
    records.apply_values(company, values, non_nullable=COMPANY_NON_NULLABLE)
    for key, old in before.items():
        if getattr(company, key) != old and company.get_field_status(key) is VerificationStatus.VERIFIED:
            company.set_field_verification(key, VerificationStatus.REQUIRES_REVIEW)
    records.commit(db)
    return company


def set_field_verification(
    db: Session,
    company: Company,
    field: str,
    status: VerificationStatus,
    *,
    source_document_id: Optional[int],
    last_verified_at: Optional[datetime],
) -> Company:
    if field not in PROFILE_FIELDS:
        raise ServiceError(422, f"Unknown profile field {field!r}. Allowed: {', '.join(PROFILE_FIELDS)}.")
    records.require_document_owned(db, source_document_id, company_id=company.id)
    company.set_field_verification(
        field, status, last_verified_at=last_verified_at, source_document_id=source_document_id
    )
    records.commit(db)
    return company


def delete_company(db: Session, company: Company, *, uploads_dir: Path, storage_dir: Path) -> None:
    """Delete the company with its projects and documents, then their stored files."""
    stored = files.collect_for_company(db, company.id)
    records.delete_record(db, company)
    files.remove_files(stored, uploads_dir=uploads_dir, storage_dir=storage_dir)


# ---------------------------------------------------------------------------
# child records
# ---------------------------------------------------------------------------
def _check_workforce(record: CompanyWorkforceRole) -> None:
    if record.available_headcount is not None and record.available_headcount > record.headcount:
        raise ServiceError(422, "available_headcount cannot exceed headcount.")


def _check_certification(record: CompanyCertification) -> None:
    if record.issued_date and record.expiry_date and record.expiry_date < record.issued_date:
        raise ServiceError(422, "expiry_date cannot be before issued_date.")


def _check_past_project(record: CompanyPastProject) -> None:
    if record.start_date and record.completion_date and record.completion_date < record.start_date:
        raise ServiceError(422, "completion_date cannot be before start_date.")


class ChildSpec:
    def __init__(
        self,
        model: type,
        label: str,
        non_nullable: tuple[str, ...],
        conflict_message: str,
        check: Optional[Callable[[Any], None]] = None,
    ) -> None:
        self.model = model
        self.label = label
        self.non_nullable = non_nullable
        self.conflict_message = conflict_message
        self.check = check


CHILDREN: dict[str, ChildSpec] = {
    "workforce-roles": ChildSpec(
        CompanyWorkforceRole,
        "Workforce role",
        ("role", "headcount", "skills"),
        "A workforce role with this department and role name already exists for the company.",
        _check_workforce,
    ),
    "equipment": ChildSpec(CompanyEquipment, "Equipment", ("name", "quantity", "ownership"), "Duplicate equipment."),
    "certifications": ChildSpec(
        CompanyCertification, "Certification", ("name",), "Duplicate certification.", _check_certification
    ),
    "past-projects": ChildSpec(
        CompanyPastProject, "Past project", ("title", "currency"), "Duplicate past project.", _check_past_project
    ),
}


def get_child(db: Session, spec: ChildSpec, company: Company, record_id: int) -> Any:
    return records.get_owned_or_404(
        db, spec.model, record_id, owner_field="company_id", owner_id=company.id, label=spec.label
    )


def create_child(db: Session, spec: ChildSpec, company: Company, values: Mapping[str, Any]) -> Any:
    values = dict(values)
    verification = values.pop("verification_status", None)
    records.require_document_owned(db, values.get("source_document_id"), company_id=company.id)
    record = spec.model(company_id=company.id)
    records.apply_values(record, values)
    if verification is not None:
        records.apply_verification(record, verification)
    if spec.check:
        spec.check(record)
    db.add(record)
    records.commit(db, conflict_message=spec.conflict_message)
    return record


def update_child(db: Session, spec: ChildSpec, company: Company, record: Any, values: Mapping[str, Any]) -> Any:
    values = dict(values)
    verification = None
    if "verification_status" in values:
        verification = values.pop("verification_status")
        if verification is None:
            raise ServiceError(422, "verification_status cannot be null.")
    records.require_document_owned(db, values.get("source_document_id"), company_id=company.id)
    records.apply_values(record, values, non_nullable=spec.non_nullable)
    if verification is not None:
        records.apply_verification(record, verification)
    if spec.check:
        spec.check(record)
    records.commit(db, conflict_message=spec.conflict_message)
    return record
