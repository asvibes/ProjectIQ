"""Response schemas for the document API. ``storage_path`` is deliberately not exposed."""
from datetime import datetime
from typing import Any, Optional

from app.models.enums import DocumentType, ProcessingStatus
from app.schemas.base import ORMModel


class DocumentRead(ORMModel):
    id: int
    company_id: Optional[int] = None
    project_id: Optional[int] = None
    document_type: DocumentType
    original_filename: str
    mime_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    sha256: Optional[str] = None
    version: int
    page_count: Optional[int] = None
    processing_status: ProcessingStatus
    processing_error: Optional[str] = None
    processed_at: Optional[datetime] = None
    summary: Optional[str] = None
    extraction_info: Optional[dict[str, Any]] = None
    chunk_count: int = 0  # not a column: filled in by the router
    created_at: datetime
    updated_at: datetime


class DocumentList(ORMModel):
    items: list[DocumentRead]
    total: int
    limit: int
    offset: int


class ChunkRead(ORMModel):
    chunk_index: int
    text: str
    char_count: int
    heading: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    location_ref: Optional[str] = None
    sheet_name: Optional[str] = None
    sources: list[dict[str, Any]]


class ChunkList(ORMModel):
    items: list[ChunkRead]
    total: int
    limit: int
    offset: int
