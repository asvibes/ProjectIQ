"""Uploaded files: tender documents (owned by a project) and company documents
(owned by the company). Exactly one owner is required."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, BigInteger, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database import Base
from app.models.enums import DocumentType, ProcessingStatus
from app.models.mixins import TimestampMixin
from app.models.types import UTCDateTime, enum_type, utcnow


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "(company_id IS NOT NULL AND project_id IS NULL) OR "
            "(company_id IS NULL AND project_id IS NOT NULL)",
            name="exactly_one_owner",
        ),
        CheckConstraint(
            "processing_status != 'failed' OR "
            "(processing_error IS NOT NULL AND length(trim(processing_error)) > 0)",
            name="failed_has_reason",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("file_size_bytes IS NULL OR file_size_bytes >= 0", name="size_non_negative"),
        CheckConstraint("page_count IS NULL OR page_count >= 0", name="pages_non_negative"),
        CheckConstraint("sha256 IS NULL OR length(sha256) = 64", name="sha256_length"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )

    document_type: Mapped[DocumentType] = mapped_column(
        enum_type(DocumentType), default=DocumentType.OTHER, nullable=False
    )

    # File metadata. The original file is preserved untouched at storage_path
    # (relative to the storage/uploads folder).
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(150))
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    page_count: Mapped[Optional[int]] = mapped_column(Integer)

    # Processing state is always visible; failures always carry a reason.
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        enum_type(ProcessingStatus), default=ProcessingStatus.QUEUED, nullable=False, index=True
    )
    processing_error: Mapped[Optional[str]] = mapped_column(Text)
    processed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    # What the ingestion reader reported: reader status, warnings, reader metadata, chunk
    # count; on failure also the stage and error type. NULL until processing has run.
    extraction_info: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    company: Mapped[Optional["Company"]] = relationship(back_populates="documents")  # noqa: F821
    project: Mapped[Optional["Project"]] = relationship(back_populates="documents")  # noqa: F821
    extracted_facts: Mapped[list["ExtractedFact"]] = relationship(  # noqa: F821
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(  # noqa: F821
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentChunk.chunk_index",
    )
    # Deleting a document keeps its requirements (source link is set to NULL by the DB).
    requirements: Mapped[list["Requirement"]] = relationship(  # noqa: F821
        back_populates="source_document", passive_deletes=True
    )

    @property
    def is_company_document(self) -> bool:
        return self.company_id is not None

    @validates("sha256")
    def _validate_sha256(self, _key: str, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip().lower()
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("sha256 must be 64 hexadecimal characters")
        return value

    def mark_done(self) -> None:
        self.processing_status = ProcessingStatus.DONE
        self.processing_error = None
        self.processed_at = utcnow()

    def mark_failed(self, reason: str) -> None:
        if not reason or not reason.strip():
            raise ValueError("A failed document needs a reason")
        self.processing_status = ProcessingStatus.FAILED
        self.processing_error = reason.strip()
        self.processed_at = utcnow()
