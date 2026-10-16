"""Document API: upload (with processing), list, retrieve, list chunks, delete.

Ownership: every document belongs to exactly one company (company documents) or project
(tender documents). Uploads carry ``company_id`` or ``project_id`` as form fields.

Errors use FastAPI's ``{"detail": "..."}`` shape: 404 unknown owner/document, 422 invalid
owner combination or document type, 413 too large, 415 unsupported type or content, 400
unusable filename or empty file.

An accepted upload answers 201 with the stored document. If extraction fails (corrupt file,
scanned PDF, ...) the document is still stored and the response shows
``processing_status = "failed"`` with ``processing_error``; it is not an HTTP error.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Company, Document, DocumentChunk, DocumentType, ProcessingStatus, Project
from app.schemas.document import ChunkList, ChunkRead, DocumentList, DocumentRead
from app.services.documents import storage
from app.services.documents.pipeline import ingest_upload
from app.services.documents.storage import UploadRejected

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

# Which document types may belong to which owner. OTHER is allowed for both.
PROJECT_DOCUMENT_TYPES = frozenset(
    {
        DocumentType.TENDER,
        DocumentType.TENDER_ADDENDUM,
        DocumentType.BILL_OF_QUANTITIES,
        DocumentType.SPECIFICATION,
        DocumentType.CONTRACT,
        DocumentType.OTHER,
    }
)
COMPANY_DOCUMENT_TYPES = frozenset(
    {
        DocumentType.CERTIFICATE,
        DocumentType.PAST_PROJECTS,
        DocumentType.EQUIPMENT_REGISTER,
        DocumentType.COMPANY_PROFILE,
        DocumentType.OTHER,
    }
)


def get_upload_dir() -> Path:
    """Dependency so tests can point uploads at a temporary directory."""
    path = get_settings().uploads_dir
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _require_exactly_one_owner(company_id: Optional[int], project_id: Optional[int]) -> None:
    if (company_id is None) == (project_id is None):
        raise HTTPException(422, "Provide exactly one of company_id or project_id.")


def _require_owner_exists(db: Session, company_id: Optional[int], project_id: Optional[int]) -> None:
    if company_id is not None and db.get(Company, company_id) is None:
        raise HTTPException(404, f"Company {company_id} not found.")
    if project_id is not None and db.get(Project, project_id) is None:
        raise HTTPException(404, f"Project {project_id} not found.")


def _resolve_document_type(requested: Optional[DocumentType], is_company: bool) -> DocumentType:
    if requested is None:
        return DocumentType.OTHER if is_company else DocumentType.TENDER
    allowed = COMPANY_DOCUMENT_TYPES if is_company else PROJECT_DOCUMENT_TYPES
    if requested not in allowed:
        owner = "company" if is_company else "project"
        raise HTTPException(
            422,
            f"Document type '{requested.value}' cannot belong to a {owner}. Allowed: "
            f"{', '.join(sorted(t.value for t in allowed))}.",
        )
    return requested


def _chunk_counts(db: Session, ids: list[int]) -> dict[int, int]:
    if not ids:
        return {}
    rows = db.execute(
        select(DocumentChunk.document_id, func.count())
        .where(DocumentChunk.document_id.in_(ids))
        .group_by(DocumentChunk.document_id)
    ).all()
    return {document_id: count for document_id, count in rows}


def _read(document: Document, chunk_count: int) -> DocumentRead:
    out = DocumentRead.model_validate(document)
    out.chunk_count = chunk_count
    return out


def _get_or_404(db: Session, document_id: int) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(404, f"Document {document_id} not found.")
    return document


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------
@router.post(
    "",
    response_model=DocumentRead,
    status_code=201,
    summary="Upload a document and process it",
)
def upload_document(
    file: UploadFile = File(...),
    company_id: Optional[int] = Form(None),
    project_id: Optional[int] = Form(None),
    document_type: Optional[DocumentType] = Form(None),
    db: Session = Depends(get_db),
    uploads_dir: Path = Depends(get_upload_dir),
) -> DocumentRead:
    """Store the original, extract its text, create traceable chunks, record the status.

    Supported: PDF, DOCX, XLSX, CSV, TXT, MD. Provide exactly one of ``company_id`` /
    ``project_id``. ``document_type`` defaults to ``tender`` for projects and ``other`` for
    companies.
    """
    _require_exactly_one_owner(company_id, project_id)
    _require_owner_exists(db, company_id, project_id)
    resolved_type = _resolve_document_type(document_type, is_company=company_id is not None)
    try:
        document = ingest_upload(
            db,
            stream=file.file,
            original_filename=file.filename,
            uploads_dir=uploads_dir,
            company_id=company_id,
            project_id=project_id,
            document_type=resolved_type,
        )
    except UploadRejected as exc:
        raise HTTPException(exc.status_code, exc.message) from exc
    return _read(document, _chunk_counts(db, [document.id]).get(document.id, 0))


@router.get("", response_model=DocumentList, summary="List documents")
def list_documents(
    company_id: Optional[int] = Query(None),
    project_id: Optional[int] = Query(None),
    processing_status: Optional[ProcessingStatus] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> DocumentList:
    if company_id is not None and project_id is not None:
        raise HTTPException(422, "Filter by company_id or project_id, not both.")
    _require_owner_exists(db, company_id, project_id)

    conditions = []
    if company_id is not None:
        conditions.append(Document.company_id == company_id)
    if project_id is not None:
        conditions.append(Document.project_id == project_id)
    if processing_status is not None:
        conditions.append(Document.processing_status == processing_status)

    total = db.scalar(select(func.count()).select_from(Document).where(*conditions)) or 0
    rows = db.scalars(
        select(Document).where(*conditions).order_by(Document.id.desc()).limit(limit).offset(offset)
    ).all()
    counts = _chunk_counts(db, [d.id for d in rows])
    return DocumentList(
        items=[_read(d, counts.get(d.id, 0)) for d in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{document_id}", response_model=DocumentRead, summary="Get one document")
def get_document(document_id: int, db: Session = Depends(get_db)) -> DocumentRead:
    document = _get_or_404(db, document_id)
    return _read(document, _chunk_counts(db, [document.id]).get(document.id, 0))


@router.get("/{document_id}/chunks", response_model=ChunkList, summary="List a document's chunks")
def list_chunks(
    document_id: int,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ChunkList:
    _get_or_404(db, document_id)
    total = (
        db.scalar(select(func.count()).select_from(DocumentChunk).where(DocumentChunk.document_id == document_id))
        or 0
    )
    rows = db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
        .limit(limit)
        .offset(offset)
    ).all()
    return ChunkList(
        items=[ChunkRead.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.delete("/{document_id}", status_code=204, summary="Delete a document and its stored file")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    uploads_dir: Path = Depends(get_upload_dir),
) -> Response:
    """Removes the row (chunks and extracted facts cascade; requirements keep their quotation
    with the source link cleared), then the stored original."""
    document = _get_or_404(db, document_id)
    storage_path = document.storage_path
    db.delete(document)
    db.commit()
    try:
        storage.remove_stored_file(storage.resolve_storage_path(uploads_dir, storage_path))
    except ValueError:
        logger.error("Refusing to delete a file outside the uploads folder: %r", storage_path)
    return Response(status_code=204)
