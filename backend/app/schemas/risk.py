"""Schemas for the risk register."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field

from app.models import RiskCategory, RiskStatus
from app.models.enums import RequirementOrigin, VerificationStatus
from app.schemas.base import ORMModel, RequestModel
from app.schemas.common import Code32, Text255


class RiskCreate(RequestModel):
    """A manually entered risk. ``score`` is not accepted: it is written by the risk-scoring
    service. ``code`` is generated (RISK-001, ...) when omitted."""

    code: Optional[Code32] = None
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    category: RiskCategory = RiskCategory.OTHER
    status: RiskStatus = RiskStatus.IDENTIFIED
    probability: Optional[int] = Field(default=None, ge=1, le=5)
    impact: Optional[int] = Field(default=None, ge=1, le=5)
    mitigation: Optional[str] = None
    owner: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = None
    source_document_id: Optional[int] = None
    page_number: Optional[int] = Field(default=None, ge=1)
    location_ref: Optional[Text255] = None
    quotation: Optional[str] = None


class RiskUpdate(RequestModel):
    code: Optional[Code32] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    category: Optional[RiskCategory] = None
    status: Optional[RiskStatus] = None
    probability: Optional[int] = Field(default=None, ge=1, le=5)
    impact: Optional[int] = Field(default=None, ge=1, le=5)
    mitigation: Optional[str] = None
    owner: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = None
    verification_status: Optional[VerificationStatus] = None
    source_document_id: Optional[int] = None
    page_number: Optional[int] = Field(default=None, ge=1)
    location_ref: Optional[Text255] = None
    quotation: Optional[str] = None


class RiskRead(ORMModel):
    id: int
    project_id: int
    source_document_id: Optional[int] = None
    code: str
    title: str
    description: Optional[str] = None
    category: RiskCategory
    status: RiskStatus
    probability: Optional[int] = None
    impact: Optional[int] = None
    score: Optional[int] = None  # null until the scoring service has run on current ratings
    mitigation: Optional[str] = None
    owner: Optional[str] = None
    notes: Optional[str] = None
    verification_status: VerificationStatus
    last_verified_at: Optional[datetime] = None
    page_number: Optional[int] = None
    location_ref: Optional[str] = None
    quotation: Optional[str] = None
    quote_verified: Optional[bool] = None
    origin: RequirementOrigin
    extractor: Optional[str] = None
    created_at: datetime
    updated_at: datetime
