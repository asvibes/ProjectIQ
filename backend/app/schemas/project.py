"""Schemas for the project API."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import AwareDatetime, Field

from app.models.enums import ProjectStatus
from app.schemas.base import ORMModel, RequestModel
from app.schemas.common import Currency, MoneyIn, Name200


class ProjectCreate(RequestModel):
    company_id: int
    name: Name200
    category: Optional[str] = Field(default=None, max_length=120)
    client: Optional[str] = Field(default=None, max_length=200)
    location: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    objectives: Optional[str] = None
    deliverables: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    currency: Optional[Currency] = None  # defaults to the configured DEFAULT_CURRENCY
    budget: Optional[MoneyIn] = None  # unknown until stated
    deadline: Optional[AwareDatetime] = None
    status: ProjectStatus = ProjectStatus.DRAFT


class ProjectUpdate(RequestModel):
    """Partial update. ``company_id`` cannot be changed."""

    name: Optional[Name200] = None
    category: Optional[str] = Field(default=None, max_length=120)
    client: Optional[str] = Field(default=None, max_length=200)
    location: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    objectives: Optional[str] = None
    deliverables: Optional[list[str]] = None
    constraints: Optional[list[str]] = None
    currency: Optional[Currency] = None
    budget: Optional[MoneyIn] = None
    deadline: Optional[AwareDatetime] = None
    status: Optional[ProjectStatus] = None


class ProjectRead(ORMModel):
    id: int
    company_id: int
    name: str
    category: Optional[str] = None
    client: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    objectives: Optional[str] = None
    deliverables: list[str]
    constraints: list[str]
    currency: str
    budget: Optional[Decimal] = None
    deadline: Optional[datetime] = None
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
