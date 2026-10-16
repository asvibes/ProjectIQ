"""Safe handling of uploaded files (untrusted input).

* The client's filename is validated and kept only as display metadata
  (``Document.original_filename``). It is never used to build a path: files are stored as
  ``<uuid4 hex><extension>`` directly inside the uploads folder.
* The upload is streamed to disk in ``CHUNK_SIZE`` blocks with a hard byte limit, so a large
  upload is never held in memory by this code. The file is created exclusively (``"xb"``):
  an existing file can never be overwritten.
* SHA-256 is computed while streaming.
* The extension must be one of the six supported types *and* the first bytes must match it
  (``%PDF-`` for PDF, a zip header for DOCX/XLSX, no binary signatures or NUL bytes for text
  formats). Deeper structure (zip contents, parsing) is checked by the ingestion readers.
* On any rejection or error the partially written file is removed.
"""
from __future__ import annotations

import codecs
import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Optional

from app.services.ingestion.sanitizer import MAX_FILE_BYTES

__all__ = [
    "ALLOWED_TYPES",
    "MAX_UPLOAD_BYTES",
    "StoredFile",
    "UploadRejected",
    "check_content",
    "mime_for",
    "remove_stored_file",
    "resolve_storage_path",
    "save_stream",
    "validate_filename",
]

logger = logging.getLogger(__name__)

# Module constants (like the ingestion limits) so tests can override them. Kept equal to the
# readers' own limit so an accepted upload can always be read.
MAX_UPLOAD_BYTES = MAX_FILE_BYTES
CHUNK_SIZE = 1024 * 1024
HEAD_BYTES = 8192
MAX_FILENAME_CHARS = 255  # Document.original_filename is String(255)

ALLOWED_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".md": "text/markdown",
}

_CONTROL_RE = re.compile("[\x00-\x1f\x7f-\x9f]")
_ZIP_MAGIC = b"PK\x03\x04"
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_TEXT_BOMS = (codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE, codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)


class UploadRejected(Exception):
    """The upload cannot be accepted. ``status_code`` is the HTTP status to answer with and
    ``message`` is safe to show to the client."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class StoredFile:
    path: Path  # absolute location of the stored original
    storage_path: str  # relative to the uploads folder; this is what Document.storage_path holds
    size: int
    sha256: str
    mime_type: str


def mime_for(extension: str) -> str:
    return ALLOWED_TYPES[extension]


def validate_filename(raw: Optional[str]) -> tuple[str, str]:
    """Return ``(display_name, extension)`` or raise :class:`UploadRejected`.

    Directory parts (``../``, ``C:\\x\\``) are dropped; the remaining base name is metadata only.
    """
    if raw is None or not raw.strip():
        raise UploadRejected(400, "The upload has no filename.")
    if _CONTROL_RE.search(raw):
        raise UploadRejected(400, "The filename contains control characters.")
    name = raw.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if name in ("", ".", ".."):
        raise UploadRejected(400, "The upload has no usable filename.")
    if len(name) > MAX_FILENAME_CHARS:
        raise UploadRejected(400, f"The filename is longer than {MAX_FILENAME_CHARS} characters.")
    extension = PurePosixPath(name).suffix.lower()
    if extension not in ALLOWED_TYPES:
        shown = extension or "(none)"
        raise UploadRejected(
            415,
            f"Unsupported file type {shown}. Allowed: {', '.join(sorted(ALLOWED_TYPES))}.",
        )
    return name, extension


def _looks_binary(head: bytes) -> bool:
    if head.startswith((b"%PDF-", _ZIP_MAGIC, _OLE_MAGIC)):
        return True
    return b"\x00" in head and not head.startswith(_TEXT_BOMS)


def check_content(extension: str, head: bytes) -> None:
    """Check that the first bytes plausibly match ``extension``; raise :class:`UploadRejected`."""
    if extension == ".pdf":
        if b"%PDF-" not in head[:1024]:
            raise UploadRejected(415, "The file does not look like a PDF (no %PDF- header).")
    elif extension in (".docx", ".xlsx"):
        label = extension[1:].upper()
        if head.startswith(_OLE_MAGIC):
            raise UploadRejected(
                415,
                f"The file is a legacy or password-protected Office file, not a {label}.",
            )
        if not head.startswith(_ZIP_MAGIC):
            raise UploadRejected(415, f"The file does not look like a {label} (not a zip container).")
    elif _looks_binary(head):
        raise UploadRejected(
            415, f"The file does not look like plain text; it has a {extension} extension."
        )


def remove_stored_file(path: Path) -> None:
    """Delete ``path`` if present. Failures are logged (never silently ignored) and not raised,
    so cleanup cannot mask the error that triggered it."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.error("Could not remove stored file %s", path, exc_info=True)


def resolve_storage_path(uploads_dir: Path, storage_path: str) -> Path:
    """Map a stored relative path to an absolute one, refusing anything outside ``uploads_dir``."""
    root = uploads_dir.resolve()
    candidate = (root / storage_path).resolve()
    if candidate == root or not candidate.is_relative_to(root):
        raise ValueError(f"Storage path escapes the uploads folder: {storage_path!r}")
    return candidate


def save_stream(
    stream: BinaryIO,
    uploads_dir: Path,
    extension: str,
    max_bytes: Optional[int] = None,
) -> StoredFile:
    """Stream ``stream`` into a new uniquely named file and return where it went.

    Raises :class:`UploadRejected` (too large, empty, content does not match the extension).
    A file is left behind only on success.
    """
    limit = MAX_UPLOAD_BYTES if max_bytes is None else max_bytes
    uploads_dir.mkdir(parents=True, exist_ok=True)
    root = uploads_dir.resolve()
    final = root / f"{uuid.uuid4().hex}{extension}"

    hasher = hashlib.sha256()
    size = 0
    head = bytearray()
    out = open(final, "xb")  # FileExistsError if taken: nothing of ours exists yet to clean up
    try:
        with out:
            while True:
                block = stream.read(CHUNK_SIZE)
                if not block:
                    break
                size += len(block)
                if size > limit:
                    raise UploadRejected(413, f"The file is larger than the limit of {limit} bytes.")
                if len(head) < HEAD_BYTES:
                    head += block[: HEAD_BYTES - len(head)]
                hasher.update(block)
                out.write(block)
        if size == 0:
            raise UploadRejected(400, "The uploaded file is empty.")
        check_content(extension, bytes(head))
    except BaseException:
        remove_stored_file(final)
        raise

    return StoredFile(
        path=final,
        storage_path=final.name,
        size=size,
        sha256=hasher.hexdigest(),
        mime_type=mime_for(extension),
    )
