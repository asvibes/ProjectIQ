"""Text sanitisation plus the types and safety helpers shared by all ingestion readers.

The task lists exactly five files, so the shared contract lives here:

* ``ExtractedDocument`` / ``TextSegment`` - the one return type of every reader.
  Segments carry ``page_number`` and ``location_ref`` (``"page 3"``, ``"Sheet BOQ!A14:D14"``,
  ``"table 2, row 5"``, ``"lines 10-14"``) which map directly onto
  ``SourceLocationMixin.page_number`` / ``location_ref`` so a later AI step can cite a
  source and the quote checker can find the quotation again.
* Exceptions - readers *raise* (nothing is returned as an "error result"), so the caller
  can turn them into ``Document.mark_failed(str(exc))``.
* ``SanitizationReport`` - nothing is removed silently: counts of removed characters are
  returned and surfaced as warnings.
* ``load_source`` / ``ensure_ooxml`` - size limits and zip-bomb checks for untrusted uploads.
  Archives are inspected, never extracted to disk.

Document content is only ever treated as data: no ``eval``/``exec``, no macro execution,
no formula evaluation, no external links followed.
"""
from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Optional, Union

__all__ = [
    "MAX_FILE_BYTES",
    "ExtractionStatus",
    "SegmentKind",
    "TextSegment",
    "ExtractedDocument",
    "SanitizationReport",
    "IngestionError",
    "UnsupportedFormatError",
    "CorruptDocumentError",
    "ExtractionFailedError",
    "EncryptedDocumentError",
    "ResourceLimitError",
    "TextDecodingError",
    "sanitize_text",
    "sanitize_text_with_report",
    "normalize_line_endings",
    "normalize_for_comparison",
    "load_source",
    "ensure_ooxml",
]

# ---------------------------------------------------------------------------
# Limits (module constants so they are easy to find and to override in tests)
# ---------------------------------------------------------------------------
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_ZIP_ENTRIES = 5_000
MAX_ZIP_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
MAX_ZIP_RATIO = 200  # uncompressed/compressed, only checked for entries > 1 MiB
_ZIP_RATIO_MIN_SIZE = 1024 * 1024

Source = Union[str, Path, bytes, bytearray, BinaryIO]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class IngestionError(Exception):
    """Base class. ``str(exc)`` is a user-presentable reason suitable for
    ``Document.mark_failed``."""


class UnsupportedFormatError(IngestionError):
    """Wrong extension, wrong magic bytes, or a format we deliberately do not read
    (legacy .doc/.xls, macro workbooks, ...)."""


class CorruptDocumentError(IngestionError):
    """The file claims to be a supported format but cannot be parsed (or is 0 bytes)."""


class ExtractionFailedError(IngestionError):
    """The file parsed, but text could not be extracted. This is *not* the same as an
    empty document - an empty document is returned with ``ExtractionStatus.EMPTY``."""


class EncryptedDocumentError(ExtractionFailedError):
    """Password-protected file that cannot be opened without a password."""


class ResourceLimitError(IngestionError):
    """File exceeds a size, page, cell, or decompression limit."""


class TextDecodingError(IngestionError):
    """Plain-text bytes could not be decoded without guessing."""


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
class ExtractionStatus(str, Enum):
    OK = "ok"
    #: Parsed fine and genuinely contains no content (0 pages, blank docx, blank workbook).
    EMPTY = "empty"
    #: PDF has pages but none has a text layer (usually scanned images). OCR is NOT
    #: implemented, so no text was recovered.
    NO_EXTRACTABLE_TEXT = "no_extractable_text"


class SegmentKind(str, Enum):
    PAGE = "page"
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    TABLE_ROW = "table_row"
    ROW = "row"  # worksheet row / CSV line


@dataclass(frozen=True)
class TextSegment:
    """One citable unit of text with its source location."""

    text: str
    kind: SegmentKind
    source_filename: str
    page_number: Optional[int] = None  # 1-based; PDFs only
    location_ref: Optional[str] = None  # free-form, e.g. "Sheet BOQ!A14:D14"
    sheet_name: Optional[str] = None
    heading_level: Optional[int] = None  # 0 = document title, 1.. = Heading N
    #: Column-aligned cell values for table/worksheet rows (blank cells are "").
    #: Authoritative for structure; ``text`` joins them with " | " for display only.
    cells: Optional[tuple[str, ...]] = None


@dataclass
class ExtractedDocument:
    filename: str
    file_type: str  # "pdf" | "docx" | "xlsx" | "txt" | "csv" | ...
    status: ExtractionStatus
    segments: list[TextSegment] = field(default_factory=list)
    page_count: Optional[int] = None  # None when the format has no fixed pages
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_text(self) -> bool:
        return any(s.text for s in self.segments)

    @property
    def full_text(self) -> str:
        return _join_segments(s for s in self.segments if s.text)

    def to_marked_text(self) -> str:
        """Text with ``[Page N]`` / ``[Sheet: X]`` markers, convenient for prompts/chunking."""
        parts: list[tuple[SegmentKind, str]] = []
        last_marker: Optional[str] = None
        for seg in self.segments:
            if not seg.text:
                continue
            marker = None
            if seg.page_number is not None:
                marker = f"[Page {seg.page_number}]"
            elif seg.sheet_name is not None:
                marker = f"[Sheet: {seg.sheet_name}]"
            if marker and marker != last_marker:
                parts.append((SegmentKind.PARAGRAPH, marker))
                last_marker = marker
            parts.append((seg.kind, seg.text))
        return _join_pairs(parts)


def _join_segments(segments: Iterable[TextSegment]) -> str:
    return _join_pairs((s.kind, s.text) for s in segments)


def _join_pairs(pairs: Iterable[tuple[SegmentKind, str]]) -> str:
    """Rows are joined by a single newline, everything else by a blank line."""
    out: list[str] = []
    prev: Optional[SegmentKind] = None
    row_kinds = (SegmentKind.ROW, SegmentKind.TABLE_ROW)
    for kind, text in pairs:
        if out:
            out.append("\n" if (kind in row_kinds and prev == kind) else "\n\n")
        out.append(text)
        prev = kind
    return "".join(out)


# ---------------------------------------------------------------------------
# Sanitiser
# ---------------------------------------------------------------------------
@dataclass
class SanitizationReport:
    """What the sanitiser changed. Removals are counted so nothing disappears silently."""

    null_bytes_removed: int = 0
    control_chars_removed: int = 0
    invisible_chars_removed: int = 0
    line_breaks_normalized: int = 0
    unicode_normalized: bool = False

    def merge(self, other: "SanitizationReport") -> None:
        self.null_bytes_removed += other.null_bytes_removed
        self.control_chars_removed += other.control_chars_removed
        self.invisible_chars_removed += other.invisible_chars_removed
        self.line_breaks_normalized += other.line_breaks_normalized
        self.unicode_normalized = self.unicode_normalized or other.unicode_normalized

    def as_dict(self) -> dict[str, Any]:
        data = {
            "null_bytes_removed": self.null_bytes_removed,
            "control_chars_removed": self.control_chars_removed,
            "invisible_chars_removed": self.invisible_chars_removed,
            "line_breaks_normalized": self.line_breaks_normalized,
            "unicode_normalized": self.unicode_normalized,
        }
        return {k: v for k, v in data.items() if v}

    def warnings(self) -> list[str]:
        """Warnings for removals only (whitespace/line-ending tidying is not a loss)."""
        out = []
        if self.null_bytes_removed:
            out.append(f"Removed {self.null_bytes_removed} null byte(s) from the extracted text.")
        if self.control_chars_removed:
            out.append(
                f"Removed {self.control_chars_removed} non-printable control character(s) "
                "from the extracted text."
            )
        return out


_LINE_BREAK_RE = re.compile(r"\r\n|\r|\x85|\u2028|\u2029")
# C0 controls except \t \n \r (and \x0b/\x0c which become newlines first), DEL, and C1 controls.
_CONTROL_RE = re.compile("[\x01-\x08\x0e-\x1f\x7f\x80-\x9f]")
# soft hyphen, zero-width space, word joiner, BOM/ZWNBSP. ZWJ/ZWNJ are kept: they are
# meaningful in several scripts.
_INVISIBLE_RE = re.compile("[\u00ad\u200b\u2060\ufeff]")
_UNICODE_SPACE_RE = re.compile("[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]")
_SPACES_RE = re.compile(r" {2,}")
_HSPACE_RE = re.compile(r"[ \t]+")
_BLANK_RUN_RE = re.compile(r"\n{3,}")


def normalize_line_endings(text: str) -> str:
    """Convert CRLF, CR, NEL, LS and PS to ``\\n``. Nothing else is touched."""
    return _LINE_BREAK_RE.sub("\n", text)


def sanitize_text_with_report(
    text: str, *, preserve_tabs: bool = False
) -> tuple[str, SanitizationReport]:
    """Clean extracted text and report what was changed.

    * removes NUL and other control characters (tab and newline are kept);
    * removes invisible characters (soft hyphen, zero-width space, BOM);
    * unifies line endings to ``\\n`` and turns form feed / vertical tab into newlines;
    * maps exotic Unicode spaces (NBSP, thin space, ideographic space) to a plain space;
    * applies Unicode NFC (canonical composition only - *not* NFKC, so ligatures,
      superscripts, currency signs and similar are never rewritten);
    * collapses runs of spaces/tabs inside a line and trims line edges
      (with ``preserve_tabs=True`` tabs are kept as column separators);
    * collapses 3+ newlines to exactly one blank line, preserving paragraph boundaries.

    Numbers, punctuation, clause numbers, currency symbols and case are untouched.
    """
    if not isinstance(text, str):
        raise TypeError(f"sanitize_text expects str, got {type(text).__name__}")
    report = SanitizationReport()

    report.null_bytes_removed = text.count("\x00")
    if report.null_bytes_removed:
        text = text.replace("\x00", "")

    text, report.line_breaks_normalized = _LINE_BREAK_RE.subn("\n", text)
    text = text.replace("\x0b", "\n").replace("\x0c", "\n")

    text, report.control_chars_removed = _CONTROL_RE.subn("", text)
    text, report.invisible_chars_removed = _INVISIBLE_RE.subn("", text)
    text = _UNICODE_SPACE_RE.sub(" ", text)

    composed = unicodedata.normalize("NFC", text)
    report.unicode_normalized = composed != text
    text = composed

    lines = []
    for line in text.split("\n"):
        if not line.strip():
            lines.append("")
        elif preserve_tabs:
            lines.append(_SPACES_RE.sub(" ", line).strip(" "))
        else:
            lines.append(_HSPACE_RE.sub(" ", line).strip())
    text = _BLANK_RUN_RE.sub("\n\n", "\n".join(lines)).strip("\n")
    return text, report


def sanitize_text(text: str, *, preserve_tabs: bool = False) -> str:
    """Like :func:`sanitize_text_with_report` but returns only the text."""
    return sanitize_text_with_report(text, preserve_tabs=preserve_tabs)[0]


_COMPARISON_TRANSLATION = str.maketrans(
    {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u2212": "-"}
)


def normalize_for_comparison(text: str) -> str:
    """Lossy normal form for *matching* (e.g. checking a quotation against a segment).

    Never store this; it is only for comparing two strings.
    """
    text = unicodedata.normalize("NFKC", sanitize_text(text)).translate(_COMPARISON_TRANSLATION)
    return " ".join(text.split()).casefold()


# ---------------------------------------------------------------------------
# Untrusted-input helpers
# ---------------------------------------------------------------------------
def load_source(
    source: Source,
    filename: Optional[str],
    allowed_extensions: Iterable[str],
    max_bytes: int = MAX_FILE_BYTES,
) -> tuple[bytes, str]:
    """Return ``(data, display_filename)`` after validating extension and size.

    ``source`` may be a path, raw bytes, or a binary file object. For bytes/file objects
    pass ``filename`` so the extension can be checked and recorded as provenance.
    ``FileNotFoundError`` propagates for missing paths. A name without extension is
    accepted; the readers then rely on content checks.
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"No such file: {path}")
        size = path.stat().st_size
        if size > max_bytes:
            raise ResourceLimitError(f"File is {size} bytes; the limit is {max_bytes} bytes.")
        data = path.read_bytes()
        name = filename or path.name
    elif isinstance(source, (bytes, bytearray)):
        data = bytes(source)
        name = filename or "<bytes>"
    elif hasattr(source, "read"):
        data = source.read(max_bytes + 1)
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("File objects must be opened in binary mode")
        data = bytes(data)
        name = filename or getattr(source, "name", None) or "<stream>"
        name = Path(str(name)).name
    else:
        raise TypeError(f"Unsupported source type: {type(source).__name__}")

    if len(data) > max_bytes:
        raise ResourceLimitError(f"File exceeds the limit of {max_bytes} bytes.")
    suffix = Path(name).suffix.lower()
    allowed = {e.lower() for e in allowed_extensions}
    if suffix and suffix not in allowed:
        raise UnsupportedFormatError(
            f"Unsupported file extension {suffix!r} for {name!r}; expected one of {sorted(allowed)}."
        )
    return data, name


_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def ensure_ooxml(data: bytes, required_member: str, label: str) -> None:
    """Validate that ``data`` is a sane OOXML zip containing ``required_member``.

    Checks entry count, total uncompressed size, per-entry compression ratio and unsafe
    member paths *before* any parser touches the file. Nothing is extracted.
    """
    if not data:
        raise CorruptDocumentError(f"The {label} file is empty (0 bytes).")
    if data.startswith(_OLE_MAGIC):
        raise UnsupportedFormatError(
            f"This is not a {label} (zip) file. It looks like a legacy Office binary or a "
            "password-protected Office file, which is not supported."
        )
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise CorruptDocumentError(f"The {label} file is corrupt or not a valid zip container.") from exc
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            raise ResourceLimitError(f"The {label} file contains too many internal parts ({len(infos)}).")
        total = 0
        for info in infos:
            parts = info.filename.replace("\\", "/").split("/")
            if info.filename.startswith(("/", "\\")) or ".." in parts:
                raise CorruptDocumentError(f"The {label} file contains an unsafe internal path.")
            total += info.file_size
            if info.file_size > _ZIP_RATIO_MIN_SIZE and (
                info.compress_size == 0 or info.file_size / info.compress_size > MAX_ZIP_RATIO
            ):
                raise ResourceLimitError(f"The {label} file has a suspicious compression ratio.")
        if total > MAX_ZIP_UNCOMPRESSED_BYTES:
            raise ResourceLimitError(f"The {label} file expands to more than the allowed size.")
        if required_member not in {i.filename for i in infos}:
            raise UnsupportedFormatError(
                f"The file is a zip archive but not a {label} (missing {required_member})."
            )