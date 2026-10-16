"""Reader for plain-text (``.txt``) and Markdown (``.md``) files.

Returns an :class:`~app.services.ingestion.sanitizer.ExtractedDocument` like every other
reader. Text is split into blocks at blank lines; each block becomes one segment whose
``location_ref`` is the *original* line range (``"line 4"`` / ``"lines 10-14"``), so a
finding can point back to the file. For Markdown, ATX headings (``# Title``) become their
own ``HEADING`` segments with a ``heading_level``; the text is kept verbatim, including the
leading ``#`` characters. Markdown is never rendered and no HTML/links are interpreted.

Encoding is never guessed:

* a UTF-8 / UTF-16 / UTF-32 byte-order mark is honoured;
* otherwise the bytes must be valid UTF-8, or :class:`TextDecodingError` is raised;
* a caller who knows better can pass ``encoding="cp1252"`` (or similar) explicitly.

Files that look binary (PDF/zip/OLE signature, or NUL bytes without a UTF-16/32 BOM) are
rejected instead of being turned into garbage text. A 0-byte file raises
``CorruptDocumentError`` (consistent with the other readers); a file that holds only
whitespace is returned with ``ExtractionStatus.EMPTY``.

Document content is untrusted data. Sanitising (control/invisible characters) is applied
but is *not* a defence against prompt injection: instructions written in the text are
returned verbatim, as text.
"""
from __future__ import annotations

import codecs
import re
from pathlib import Path
from typing import Optional

from app.services.ingestion.sanitizer import (
    MAX_FILE_BYTES,
    CorruptDocumentError,
    ExtractedDocument,
    ExtractionStatus,
    SanitizationReport,
    SegmentKind,
    Source,
    TextDecodingError,
    TextSegment,
    UnsupportedFormatError,
    load_source,
    normalize_line_endings,
    sanitize_text_with_report,
)

__all__ = ["TEXT_EXTENSIONS", "read_text"]

TEXT_EXTENSIONS = (".txt", ".text", ".md", ".markdown")
_MARKDOWN_EXTENSIONS = (".md", ".markdown")

# UTF-32 LE starts with the UTF-16 LE BOM, so UTF-32 must be tested first.
_BOMS = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)
_BINARY_SIGNATURES = (
    (b"%PDF-", "a PDF"),
    (b"PK\x03\x04", "a zip-based file (for example DOCX/XLSX)"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "a legacy Office file"),
)
_BINARY_SNIFF_BYTES = 8192

_ATX_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(?=\S)")
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _decode(data: bytes, encoding: Optional[str], name: str) -> tuple[str, str]:
    """Return ``(text, encoding_used)`` or raise. Never guesses an encoding."""
    for signature, label in _BINARY_SIGNATURES:
        if data.startswith(signature):
            raise UnsupportedFormatError(
                f"{name!r} looks like {label}, not a plain-text file."
            )

    if encoding is not None:
        try:
            codecs.lookup(encoding)
        except LookupError:
            raise TextDecodingError(f"Unknown text encoding {encoding!r}.") from None
        try:
            return data.decode(encoding), encoding.lower()
        except UnicodeDecodeError as exc:
            raise TextDecodingError(
                f"The file could not be decoded as {encoding} (invalid byte at offset {exc.start})."
            ) from exc

    for bom, codec in _BOMS:
        if data.startswith(bom):
            try:
                return data.decode(codec), codec
            except UnicodeDecodeError as exc:
                raise TextDecodingError(
                    f"The file has a {codec} byte-order mark but is not valid {codec} "
                    f"(invalid byte at offset {exc.start})."
                ) from exc

    if b"\x00" in data[:_BINARY_SNIFF_BYTES]:
        raise UnsupportedFormatError(
            f"{name!r} contains NUL bytes: it looks binary, or is UTF-16/32 without a "
            "byte-order mark. Re-save it as UTF-8."
        )
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError as exc:
        raise TextDecodingError(
            f"The file is not valid UTF-8 (invalid byte at offset {exc.start}) and has no "
            "byte-order mark. The encoding is not guessed: re-save the file as UTF-8 or "
            "pass the encoding explicitly."
        ) from exc


def _line_ref(start: int, end: int) -> str:
    return f"line {start}" if start == end else f"lines {start}-{end}"


def read_text(
    source: Source,
    filename: Optional[str] = None,
    *,
    encoding: Optional[str] = None,
    max_bytes: int = MAX_FILE_BYTES,
) -> ExtractedDocument:
    """Extract a ``.txt`` / ``.md`` file.

    ``source`` is a path, bytes or binary file object (see ``load_source``); pass
    ``filename`` for bytes/streams so the extension (and thus Markdown handling) is known.
    Raises :class:`IngestionError` subclasses; never returns an "error result".
    """
    data, name = load_source(source, filename, TEXT_EXTENSIONS, max_bytes)
    if not data:
        raise CorruptDocumentError("The text file is empty (0 bytes).")

    text, used_encoding = _decode(data, encoding, name)
    is_markdown = Path(name).suffix.lower() in _MARKDOWN_EXTENSIONS

    report = SanitizationReport()
    segments: list[TextSegment] = []

    def emit(kind: SegmentKind, raw: str, start: int, end: int, level: Optional[int] = None) -> None:
        cleaned, part = sanitize_text_with_report(raw)
        report.merge(part)
        if not cleaned:
            return
        segments.append(
            TextSegment(
                text=cleaned,
                kind=kind,
                source_filename=name,
                location_ref=_line_ref(start, end),
                heading_level=level,
            )
        )

    lines = normalize_line_endings(text).split("\n")
    block: list[str] = []
    block_start = block_end = 0
    fence: Optional[str] = None  # the opening fence string while inside a Markdown code block

    def flush() -> None:
        nonlocal block
        if block:
            emit(SegmentKind.PARAGRAPH, "\n".join(block), block_start, block_end)
            block = []

    for number, line in enumerate(lines, start=1):
        if is_markdown:
            match = _FENCE_RE.match(line)
            if match:
                marker = match.group(1)
                if fence is None:
                    fence = marker
                elif marker[0] == fence[0] and len(marker) >= len(fence):
                    fence = None
        if not line.strip():
            flush()
            continue
        if is_markdown and fence is None:
            heading = _ATX_HEADING_RE.match(line)
            if heading:
                flush()
                emit(SegmentKind.HEADING, line, number, number, len(heading.group(1)))
                continue
        if not block:
            block_start = number
        block.append(line)
        block_end = number
    flush()

    line_count = len(lines) - (1 if lines and lines[-1] == "" else 0)
    return ExtractedDocument(
        filename=name,
        file_type="md" if is_markdown else "txt",
        status=ExtractionStatus.OK if segments else ExtractionStatus.EMPTY,
        segments=segments,
        page_count=None,
        warnings=report.warnings(),
        metadata={
            "encoding": used_encoding,
            "line_count": line_count,
            "sanitization": report.as_dict(),
        },
    )