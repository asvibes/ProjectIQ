"""Upload -> store -> extract -> chunk -> persist, for one document.

Outcome rules (the point of this module):

* A rejected upload (bad type/content, too large, empty) leaves no database row and no file.
* An accepted upload always gets a ``Document`` row that references its preserved original.
* Extraction that fails or finds no text (reader exception, scanned PDF, blank document) ends
  as ``FAILED`` with a reason: it is never marked ``DONE``. The row and original file are kept
  so the failure is visible to the user.
* Chunks and ``mark_done()`` are written in one transaction; if that transaction fails nothing
  of it is kept and the document is marked ``FAILED``.
* If even the failure cannot be recorded, the row and the file are removed again and the error
  propagates, so there is never a row without a file or a file without a row.

Nothing here calls an AI model; document text is stored verbatim as data.
Known limitation: extraction runs synchronously in the request and has no wall-clock timeout
(pypdf offers none; see the note in ``pdf_reader``).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, BinaryIO, Callable, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk, DocumentType, ProcessingStatus
from app.services.documents import storage
from app.services.ingestion.chunker import DEFAULT_MAX_CHARS, Chunk, chunk_document
from app.services.ingestion.docx_reader import read_docx
from app.services.ingestion.pdf_reader import read_pdf
from app.services.ingestion.sanitizer import ExtractedDocument, ExtractionStatus, IngestionError
from app.services.ingestion.text_reader import read_text
from app.services.ingestion.xlsx_reader import read_csv, read_xlsx

__all__ = ["CHUNK_MAX_CHARS", "READERS", "ingest_upload", "process_document"]

logger = logging.getLogger(__name__)

CHUNK_MAX_CHARS = DEFAULT_MAX_CHARS
MAX_WARNINGS_STORED = 100
MAX_REASON_CHARS = 2000

READERS: dict[str, Callable[..., ExtractedDocument]] = {
    ".pdf": read_pdf,
    ".docx": read_docx,
    ".xlsx": read_xlsx,
    ".csv": read_csv,
    ".txt": read_text,
    ".md": read_text,
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _info(extracted: ExtractedDocument, chunk_count: int, max_chars: int, **extra: Any) -> dict:
    return _json_safe(
        {
            "reader_status": extracted.status.value,
            "file_type": extracted.file_type,
            "segment_count": len(extracted.segments),
            "chunk_count": chunk_count,
            "chunk_max_chars": max_chars,
            "warnings": list(extracted.warnings[:MAX_WARNINGS_STORED]),
            "metadata": extracted.metadata,
            **extra,
        }
    )


def _no_text_reason(extracted: ExtractedDocument) -> str:
    if extracted.status is ExtractionStatus.NO_EXTRACTABLE_TEXT:
        base = "No text could be extracted from this document."
    elif extracted.status is ExtractionStatus.EMPTY:
        base = "The document contains no text."
    else:
        base = "The document produced no text chunks."
    return f"{base} {' '.join(extracted.warnings)}".strip()


def _chunk_row(document_id: int, chunk: Chunk) -> DocumentChunk:
    return DocumentChunk(
        document_id=document_id,
        chunk_index=chunk.index,
        text=chunk.text,
        char_count=chunk.char_count,
        heading=chunk.heading,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        location_ref=chunk.location_ref,
        sheet_name=chunk.sheet_name,
        sources=[
            {
                "segment_index": s.segment_index,
                "chunk_start": s.chunk_start,
                "chunk_end": s.chunk_end,
                "segment_start": s.segment_start,
                "segment_end": s.segment_end,
                "kind": s.kind.value,
                "page_number": s.page_number,
                "location_ref": s.location_ref,
                "sheet_name": s.sheet_name,
            }
            for s in chunk.sources
        ],
    )


def _record_failure(
    db: Session,
    document: Document,
    reason: str,
    info: dict,
    page_count: Optional[int] = None,
) -> Document:
    db.rollback()  # drop anything half-written by the failed step
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    document.mark_failed(reason[:MAX_REASON_CHARS] or "Processing failed for an unknown reason.")
    document.extraction_info = info
    if page_count is not None:
        document.page_count = page_count
    db.commit()
    return document


def _store_result(
    db: Session, document: Document, extracted: ExtractedDocument, chunks: list[Chunk], max_chars: int
) -> None:
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    db.add_all([_chunk_row(document.id, c) for c in chunks])
    document.page_count = extracted.page_count
    document.extraction_info = _info(extracted, len(chunks), max_chars)
    document.mark_done()
    db.commit()  # chunks, page count, info and DONE become visible together or not at all


# ---------------------------------------------------------------------------
# processing
# ---------------------------------------------------------------------------
def process_document(
    db: Session, document: Document, path: Path, *, max_chars: int = CHUNK_MAX_CHARS
) -> Document:
    """Extract and chunk the stored original of ``document``.

    Processing problems never raise: they are recorded on the document as ``FAILED`` with a
    reason. Only a failure to record the outcome in the database propagates.
    """
    extension = Path(document.original_filename).suffix.lower()
    document.processing_status = ProcessingStatus.EXTRACTING
    document.processing_error = None
    db.commit()

    try:
        reader = READERS[extension]
        extracted = reader(path, document.original_filename, max_bytes=storage.MAX_UPLOAD_BYTES)
        chunks = chunk_document(extracted, max_chars=max_chars)
    except IngestionError as exc:
        return _record_failure(
            db, document, str(exc), {"stage": "extraction", "error_type": type(exc).__name__}
        )
    except Exception as exc:  # noqa: BLE001 - a parser bug must not leave the document "extracting"
        logger.exception("Unexpected error while extracting document %s", document.id)
        return _record_failure(
            db,
            document,
            f"Unexpected error while reading the document ({type(exc).__name__}).",
            {"stage": "extraction", "error_type": type(exc).__name__, "unexpected": True},
        )

    if extracted.status is not ExtractionStatus.OK or not chunks:
        return _record_failure(
            db,
            document,
            _no_text_reason(extracted),
            _info(extracted, 0, max_chars, stage="extraction", error_type="NoExtractableText"),
            page_count=extracted.page_count,
        )

    try:
        _store_result(db, document, extracted, chunks, max_chars)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Could not save extraction result for document %s", document.id)
        db.rollback()
        return _record_failure(
            db,
            document,
            "The extracted content could not be saved to the database.",
            _info(extracted, 0, max_chars, stage="storage", error_type=type(exc).__name__),
        )
    return document


def _discard(db: Session, document_id: int, path: Path) -> None:
    """Undo an upload whose outcome could not be recorded: no row, no file."""
    db.rollback()
    try:
        row = db.get(Document, document_id)
        if row is not None:
            db.delete(row)
            db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.error("Could not remove document row %s while discarding upload", document_id, exc_info=True)
    storage.remove_stored_file(path)


def ingest_upload(
    db: Session,
    *,
    stream: BinaryIO,
    original_filename: Optional[str],
    uploads_dir: Path,
    company_id: Optional[int],
    project_id: Optional[int],
    document_type: DocumentType,
    max_bytes: Optional[int] = None,
) -> Document:
    """Validate, store, record and process one upload. Ownership must already be validated.

    Raises :class:`storage.UploadRejected` for a bad upload (nothing is kept).
    """
    name, extension = storage.validate_filename(original_filename)
    stored = storage.save_stream(stream, uploads_dir, extension, max_bytes)

    document_id: Optional[int] = None
    try:
        owner = Document.company_id == company_id if company_id is not None else Document.project_id == project_id
        latest = db.scalar(
            select(func.max(Document.version)).where(owner, Document.original_filename == name)
        )
        document = Document(
            company_id=company_id,
            project_id=project_id,
            document_type=document_type,
            original_filename=name,
            storage_path=stored.storage_path,
            mime_type=stored.mime_type,  # from our extension table, never the client's header
            file_size_bytes=stored.size,
            sha256=stored.sha256,
            version=(latest or 0) + 1,
            processing_status=ProcessingStatus.QUEUED,
        )
        db.add(document)
        db.commit()
        document_id = document.id
        return process_document(db, document, stored.path)
    except BaseException:
        if document_id is None:
            db.rollback()
            storage.remove_stored_file(stored.path)
        else:
            _discard(db, document_id, stored.path)
        raise
