"""Schemas for the company-project fit summary."""
from __future__ import annotations

from pydantic import Field

from app.schemas.base import ORMModel, RequestModel


class FitSummary(ORMModel):
    """Counts of stored requirement states. This is a summary of recorded data, not a
    matching result: no automated matching has been run by this endpoint."""

    project_id: int
    company_id: int
    total_requirements: int
    by_match_status: dict[str, int]
    mandatory_by_match_status: dict[str, int]
    mandatory_unspecified: int  # requirements where the source does not say mandatory or not
    unreviewed_requirements: int  # verification status still "Requires review"
    automated_matching_available: bool
    basis: str


class FitRunRequest(RequestModel):
    requirement_ids: list[int] = Field(default_factory=list)
