"""A size-bounded piece of a document's extracted text, with its source locations.

Chunks are produced by ``app.services.ingestion.chunker`` during upload processing and
stored verbatim (the text is untrusted data). ``sources`` keeps, for every segment the
chunk was built from, the character spans inside the chunk and inside the original
segment plus page / location / sheet, so a quotation found in a chunk can be traced back
to its exact page, paragraph, row or cell range.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin


class DocumentChunk(TimestampMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_index"),
        CheckConstraint("chunk_index >= 0", name="index_non_negative"),
        CheckConstraint("char_count >= 0", name="chars_non_negative"),
        CheckConstraint("length(trim(text)) > 0", name="text_not_blank"),
        CheckConstraint("page_start IS NULL OR page_start >= 1", name="page_start_positive"),
        CheckConstraint(
            "page_end IS NULL OR page_start IS NULL OR page_end >= page_start",
            name="page_range_ordered",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-based, document order
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[Optional[str]] = mapped_column(Text)  # nearest heading at/before the chunk

    # Citation for the whole chunk (PDF pages only; NULL for formats without pages).
    page_start: Mapped[Optional[int]] = mapped_column(Integer)
    page_end: Mapped[Optional[int]] = mapped_column(Integer)
    # e.g. "page 3", "pages 3-5", "Sheet BOQ!A2:D2 to Sheet BOQ!A40:D40". Text, not a short
    # String: a range of two long references can exceed 255 characters.
    location_ref: Mapped[Optional[str]] = mapped_column(Text)
    sheet_name: Mapped[Optional[str]] = mapped_column(String(255))

    # One entry per ChunkSource: segment_index, chunk_start/end, segment_start/end, kind,
    # page_number, location_ref, sheet_name.
    sources: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    document: Mapped["Document"] = relationship(back_populates="chunks")  # noqa: F821
