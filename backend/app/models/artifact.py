"""Generated project outputs (FR-25): briefings and registers exported as DOCX, PPTX or CSV.

An artifact is either a stored file (``storage_path``, relative to the storage folder and
never absolute) or inline text (``content``, e.g. a Markdown briefing draft); at least one is
required. The file bytes themselves are not kept in the database. ``extra`` holds free-form
metadata such as the scenario or financial model the output was generated from; it must not
contain secrets or raw document text.
"""
from __future__ import annotations

import enum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Optional

from sqlalchemy import JSON, BigInteger, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship, validates

from app.database import Base
from app.models.mixins import TimestampMixin
from app.models.types import enum_type


class ArtifactType(str, enum.Enum):
    BRIEFING = "briefing"
    REQUIREMENTS_REGISTER = "requirements_register"
    RISK_REGISTER = "risk_register"
    FINANCIAL_SUMMARY = "financial_summary"
    SCENARIO_COMPARISON = "scenario_comparison"
    OTHER = "other"


class ArtifactFormat(str, enum.Enum):
    DOCX = "docx"
    PPTX = "pptx"
    CSV = "csv"
    JSON = "json"
    MARKDOWN = "markdown"
    OTHER = "other"


class Artifact(TimestampMixin, Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
        CheckConstraint(
            "storage_path IS NOT NULL OR content IS NOT NULL", name="has_storage_or_content"
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("file_size_bytes IS NULL OR file_size_bytes >= 0", name="size_non_negative"),
        CheckConstraint("sha256 IS NULL OR length(sha256) = 64", name="sha256_length"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    artifact_type: Mapped[ArtifactType] = mapped_column(
        enum_type(ArtifactType), default=ArtifactType.OTHER, nullable=False, index=True
    )
    file_format: Mapped[ArtifactFormat] = mapped_column(
        enum_type(ArtifactFormat), default=ArtifactFormat.OTHER, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Content reference: a stored file and/or inline text.
    storage_path: Mapped[Optional[str]] = mapped_column(String(500), unique=True)
    content: Mapped[Optional[str]] = mapped_column(Text)
    mime_type: Mapped[Optional[str]] = mapped_column(String(150))
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # What produced it, e.g. "briefing_v1" or "docx_builder"; no prompts or responses.
    generated_by: Mapped[Optional[str]] = mapped_column(String(120))
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # The reverse side (``Project.artifacts``) is created here so project.py stays untouched.
    project: Mapped["Project"] = relationship(  # noqa: F821
        backref=backref(
            "artifacts",
            cascade="all, delete-orphan",
            passive_deletes=True,
            order_by="Artifact.id",
        )
    )

    @validates("storage_path")
    def _validate_storage_path(self, _key: str, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("storage_path cannot be blank")
        posix, windows = PurePosixPath(value), PureWindowsPath(value)
        if posix.is_absolute() or windows.is_absolute() or windows.drive:
            raise ValueError("storage_path must be relative to the storage folder")
        if ".." in posix.parts or ".." in windows.parts:
            raise ValueError("storage_path must not contain '..'")
        return value

    @validates("sha256")
    def _validate_sha256(self, _key: str, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip().lower()
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("sha256 must be 64 hexadecimal characters")
        return value

    @validates("extra")
    def _validate_extra(self, _key: str, value: Any) -> dict:
        value = {} if value is None else value
        if not isinstance(value, dict):
            raise ValueError("extra must be an object")
        return value