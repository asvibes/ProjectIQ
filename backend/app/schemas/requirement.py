"""Schemas for tender requirements."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import AwareDatetime, Field

from app.models.enums import (
    MatchStatus,
    RequirementCategory,
    RequirementOrigin,
    VerificationStatus,
)
from app.schemas.base import ORMModel, RequestModel
from app.schemas.common import Code32


class RequirementCreate(RequestModel):
    """A manually entered requirement. ``origin`` is always ``manual``; ``code`` is generated
    (REQ-001, REQ-002, ...) when omitted."""

    code: Optional[Code32] = None
    description: str = Field(min_length=1)
    category: RequirementCategory = RequirementCategory.OTHER
    is_mandatory: Optional[bool] = None  # null = the source does not say
    deadline: Optional[AwareDatetime] = None
    source_document_id: Optional[int] = None
    page_number: Optional[int] = Field(default=None, ge=1)
    location_ref: Optional[str] = Field(default=None, max_length=255)
    quotation: Optional[str] = None
    match_status: MatchStatus = MatchStatus.UNKNOWN
    evidence_summary: Optional[str] = None
    missing_evidence: Optional[str] = None
    assigned_role: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = None


class RequirementUpdate(RequestModel):
    code: Optional[Code32] = None
    description: Optional[str] = Field(default=None, min_length=1)
    category: Optional[RequirementCategory] = None
    is_mandatory: Optional[bool] = None
    deadline: Optional[AwareDatetime] = None
    source_document_id: Optional[int] = None
    page_number: Optional[int] = Field(default=None, ge=1)
    location_ref: Optional[str] = Field(default=None, max_length=255)
    quotation: Optional[str] = None
    match_status: Optional[MatchStatus] = None
    evidence_summary: Optional[str] = None
    missing_evidence: Optional[str] = None
    verification_status: Optional[VerificationStatus] = None
    assigned_role: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = None


class RequirementRead(ORMModel):
    id: int
    project_id: int
    source_document_id: Optional[int] = None
    code: str
    description: str
    category: RequirementCategory
    is_mandatory: Optional[bool] = None
    deadline: Optional[datetime] = None
    match_status: MatchStatus
    evidence_summary: Optional[str] = None
    missing_evidence: Optional[str] = None
    verification_status: VerificationStatus
    last_verified_at: Optional[datetime] = None
    page_number: Optional[int] = None
    location_ref: Optional[str] = None
    quotation: Optional[str] = None
    quote_verified: Optional[bool] = None  # set by the quote checker, never by clients
    origin: RequirementOrigin
    extractor: Optional[str] = None
    assigned_role: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
