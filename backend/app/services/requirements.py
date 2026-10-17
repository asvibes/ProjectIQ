"""Rules for tender requirements managed through the API."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.models import Project, Requirement, RequirementOrigin, VerificationStatus
from app.services import records
from app.services.errors import ServiceError

NON_NULLABLE = ("code", "description", "category", "match_status")


def create_requirement(db: Session, project: Project, values: Mapping[str, Any]) -> Requirement:
    values = dict(values)
    records.require_document_owned(db, values.get("source_document_id"), project_id=project.id)
    code = values.pop("code", None) or records.next_code(db, Requirement, project.id, "REQ")
    values.update(project_id=project.id, code=code, origin=RequirementOrigin.MANUAL)
    return records.create_record(
        db, Requirement, values, conflict_message=f"Requirement code {code} already exists in this project."
    )


def update_requirement(
    db: Session, project: Project, requirement: Requirement, values: Mapping[str, Any]
) -> Requirement:
    values = dict(values)
    verification = None
    if "verification_status" in values:
        verification = values.pop("verification_status")
        if verification is None:
            raise ServiceError(422, "verification_status cannot be null.")
    records.require_document_owned(db, values.get("source_document_id"), project_id=project.id)
    records.apply_values(requirement, values, non_nullable=NON_NULLABLE)
    if verification is not None:
        records.apply_verification(requirement, verification)
    records.commit(db, conflict_message="Requirement code already exists in this project.")
    return requirement


def set_verification(db: Session, requirement: Requirement, status: VerificationStatus) -> Requirement:
    records.apply_verification(requirement, status)
    records.commit(db)
    return requirement
