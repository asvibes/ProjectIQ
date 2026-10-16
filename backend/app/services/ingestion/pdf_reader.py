"""PDF reader: text layer only, page by page, with 1-based page numbers.

Each page that has text becomes one ``SegmentKind.PAGE`` segment with ``page_number=N`` and
``location_ref="page N"``.

**OCR is not implemented and is never pretended.** If a page has no text layer it produces
no segment and is listed in ``metadata["pages_without_text"]`` plus a warning. If *no* page
has text, the result has ``ExtractionStatus.NO_EXTRACTABLE_TEXT`` (typical of scanned
documents). ``metadata["ocr_performed"]`` is always ``False``.

Safety notes (the file is untrusted):

* size and extension are checked by ``load_source`` before parsing; the ``%PDF-`` header is
  required;
* page count and total extracted characters are capped (``MAX_PDF_PAGES``,
  ``MAX_EXTRACTED_CHARS``);
* nothing in the PDF is executed or followed (JavaScript, launch actions, links, embedded
  files are ignored), and PDF "document info" metadata is deliberately not copied;
* a PDF that needs a password raises ``EncryptedDocumentError``; one that only has an
  owner password (empty user password) is opened and reported in the metadata.

Known limitation: pypdf has no wall-clock timeout, and a crafted PDF can be slow to parse.
When the upload pipeline is built, run extraction in a worker with a timeout.
"""
from __future__ import annotations

import io
from typing import Optional

from pypdf import PdfReader
from pypdf.errors import DependencyError

from app.services.ingestion.sanitizer import (
    MAX_FILE_BYTES,
    CorruptDocumentError,
    EncryptedDocumentError,
    ExtractedDocument,
    ExtractionFailedError,
    ExtractionStatus,
    IngestionError,
    ResourceLimitError,
    SanitizationReport,
    SegmentKind,
    Source,
    TextSegment,
    UnsupportedFormatError,
    load_source,
    sanitize_text_with_report,
)

__all__ = ["MAX_PDF_PAGES", "MAX_EXTRACTED_CHARS", "read_pdf"]

MAX_PDF_PAGES = 2_000
MAX_EXTRACTED_CHARS = 20_000_000

_PDF_MAGIC = b"%PDF-"
_HEADER_SCAN_BYTES = 1024  # the PDF specification allows the header within the first 1024 bytes
_MAX_PAGES_IN_MESSAGE = 15


def _page_list(pages: list[int]) -> str:
    shown = ", ".join(str(p) for p in pages[:_MAX_PAGES_IN_MESSAGE])
    extra = len(pages) - _MAX_PAGES_IN_MESSAGE
    return f"{shown} (and {extra} more)" if extra > 0 else shown


def _open_reader(data: bytes) -> tuple[PdfReader, bool, int]:
    """Parse the container. Returns ``(reader, was_encrypted, page_count)``."""
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        encrypted = bool(reader.is_encrypted)
        if encrypted:
            try:
                opened = reader.decrypt("")
            except DependencyError as exc:
                raise EncryptedDocumentError(
                    "The PDF is encrypted with AES, which needs the optional 'cryptography' "
                    "package to open. Install it, or remove the PDF's encryption."
                ) from exc
            if not opened:
                raise EncryptedDocumentError(
                    "The PDF is password-protected and cannot be opened without a password."
                )
        return reader, encrypted, len(reader.pages)
    except IngestionError:
        raise
    except MemoryError as exc:
        raise ResourceLimitError("The PDF needs more memory to parse than is allowed.") from exc
    except Exception as exc:  # noqa: BLE001 - pypdf raises many types on hostile input
        raise CorruptDocumentError(
            f"The PDF file is corrupt or could not be parsed ({type(exc).__name__})."
        ) from exc


def read_pdf(
    source: Source,
    filename: Optional[str] = None,
    *,
    max_bytes: int = MAX_FILE_BYTES,
) -> ExtractedDocument:
    """Extract the text layer of a PDF, one segment per page that has text.

    Raises :class:`IngestionError` subclasses (``UnsupportedFormatError``,
    ``CorruptDocumentError``, ``EncryptedDocumentError``, ``ResourceLimitError``,
    ``ExtractionFailedError``); never returns an "error result".
    """
    data, name = load_source(source, filename, (".pdf",), max_bytes)
    if not data:
        raise CorruptDocumentError("The PDF file is empty (0 bytes).")
    if _PDF_MAGIC not in data[:_HEADER_SCAN_BYTES]:
        raise UnsupportedFormatError("The file does not start with a PDF header (%PDF-).")

    reader, was_encrypted, page_count = _open_reader(data)
    if page_count > MAX_PDF_PAGES:
        raise ResourceLimitError(f"The PDF has {page_count} pages; the limit is {MAX_PDF_PAGES}.")

    report = SanitizationReport()
    segments: list[TextSegment] = []
    pages_without_text: list[int] = []
    failed_pages: list[int] = []
    total_chars = 0

    for number in range(1, page_count + 1):
        try:
            raw = reader.pages[number - 1].extract_text() or ""
        except MemoryError as exc:
            raise ResourceLimitError("Extracting a PDF page needs more memory than is allowed.") from exc
        except Exception:  # noqa: BLE001 - one bad page must not hide the others
            failed_pages.append(number)
            continue
        text, part = sanitize_text_with_report(raw)
        report.merge(part)
        total_chars += len(text)
        if total_chars > MAX_EXTRACTED_CHARS:
            raise ResourceLimitError(
                f"The PDF text exceeds the limit of {MAX_EXTRACTED_CHARS} characters."
            )
        if not text:
            pages_without_text.append(number)
            continue
        segments.append(
            TextSegment(
                text=text,
                kind=SegmentKind.PAGE,
                source_filename=name,
                page_number=number,
                location_ref=f"page {number}",
            )
        )

    if page_count and len(failed_pages) == page_count:
        raise ExtractionFailedError("Text extraction failed on every page of the PDF.")

    warnings = report.warnings()
    if failed_pages:
        warnings.append(
            f"Text extraction failed on page(s) {_page_list(failed_pages)}; they are missing."
        )

    if page_count == 0:
        status = ExtractionStatus.EMPTY
        warnings.append("The PDF contains no pages.")
    elif not segments:
        status = ExtractionStatus.NO_EXTRACTABLE_TEXT
        warnings.append(
            f"None of the {page_count} page(s) has a text layer (the document is probably "
            "scanned images). OCR is not implemented, so no text was extracted."
        )
    else:
        status = ExtractionStatus.OK
        if pages_without_text:
            warnings.append(
                f"Page(s) {_page_list(pages_without_text)} have no text layer (possibly scanned "
                "or image-only). OCR is not implemented, so any text on them was not extracted."
            )

    return ExtractedDocument(
        filename=name,
        file_type="pdf",
        status=status,
        segments=segments,
        page_count=page_count,
        warnings=warnings,
        metadata={
            "pages_without_text": pages_without_text,
            "failed_pages": failed_pages,
            "ocr_performed": False,
            "was_encrypted": was_encrypted,
            "sanitization": report.as_dict(),
        },
    )