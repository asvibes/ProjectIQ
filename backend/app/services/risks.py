"""Rules for the risk register.

``Risk.score`` is derived data owned by the risk-scoring service, which is not implemented.
The API therefore never accepts a score, and clears a stored one when probability or impact
change, because the old score no longer matches the ratings.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.models import Project, Risk, RequirementOrigin, VerificationStatus
from app.services import records
from app.services.errors import ServiceError

NON_NULLABLE = ("code", "title", "category", "status")


def create_risk(db: Session, project: Project, values: Mapping[str, Any]) -> Risk:
    values = dict(values)
    records.require_document_owned(db, values.get("source_document_id"), project_id=project.id)
    code = values.pop("code", None) or records.next_code(db, Risk, project.id, "RISK")
    values.update(project_id=project.id, code=code, origin=RequirementOrigin.MANUAL)
    return records.create_record(
        db, Risk, values, conflict_message=f"Risk code {code} already exists in this project."
    )


def update_risk(db: Session, project: Project, risk: Risk, values: Mapping[str, Any]) -> Risk:
    values = dict(values)
    verification = None
    if "verification_status" in values:
        verification = values.pop("verification_status")
        if verification is None:
            raise ServiceError(422, "verification_status cannot be null.")
    records.require_document_owned(db, values.get("source_document_id"), project_id=project.id)

    ratings_before = (risk.probability, risk.impact)
    records.apply_values(risk, values, non_nullable=NON_NULLABLE)
    if (risk.probability, risk.impact) != ratings_before:
        risk.score = None
    if verification is not None:
        records.apply_verification(risk, verification)
    records.commit(db, conflict_message="Risk code already exists in this project.")
    return risk


def set_verification(db: Session, risk: Risk, status: VerificationStatus) -> Risk:
    records.apply_verification(risk, status)
    records.commit(db)
    return risk
