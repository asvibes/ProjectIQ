"""Summary of the requirement states stored for a project.

Counting only: no matching is performed and no score or recommendation is produced. The
automated matcher (``services/analysis/requirement_matcher``) is not implemented yet.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MatchStatus, Project, Requirement, VerificationStatus

BASIS = (
    "Counts of the match_status and verification_status values currently stored on this "
    "project's requirements. No automated matching has been run; Unknown means not assessed."
)


def summarise(db: Session, project: Project) -> dict[str, Any]:
    by_match = {status.value: 0 for status in MatchStatus}
    mandatory_by_match = {status.value: 0 for status in MatchStatus}

    for match_status, is_mandatory, count in db.execute(
        select(Requirement.match_status, Requirement.is_mandatory, func.count())
        .where(Requirement.project_id == project.id)
        .group_by(Requirement.match_status, Requirement.is_mandatory)
    ).all():
        by_match[match_status.value] += count
        if is_mandatory is True:
            mandatory_by_match[match_status.value] += count

    base = (Requirement.project_id == project.id,)
    unspecified = db.scalar(
        select(func.count()).select_from(Requirement).where(*base, Requirement.is_mandatory.is_(None))
    )
    unreviewed = db.scalar(
        select(func.count())
        .select_from(Requirement)
        .where(*base, Requirement.verification_status == VerificationStatus.REQUIRES_REVIEW)
    )
    return {
        "project_id": project.id,
        "company_id": project.company_id,
        "total_requirements": sum(by_match.values()),
        "by_match_status": by_match,
        "mandatory_by_match_status": mandatory_by_match,
        "mandatory_unspecified": unspecified or 0,
        "unreviewed_requirements": unreviewed or 0,
        "automated_matching_available": False,
        "basis": BASIS,
    }
