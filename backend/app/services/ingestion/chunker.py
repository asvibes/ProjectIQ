"""Split an :class:`ExtractedDocument` into size-bounded chunks that keep their provenance.

Guarantees
----------
* **Order**: chunks follow document order; nothing is reordered, merged across files, or dropped.
* **Provenance**: every chunk lists the segments it was built from (``Chunk.sources``). Each
  :class:`ChunkSource` records the segment index, page number, ``location_ref``, sheet name,
  and the character span both inside the chunk text and inside the original segment text, so a
  quotation found in a chunk can be traced to its exact page / sheet / row / paragraph.
* **Faithful text**: ``chunk.text`` is built from the segment texts verbatim, joined the same
  way as ``ExtractedDocument.full_text`` (rows by one newline, everything else by a blank
  line). A document that fits in one chunk therefore has ``chunk.text == full_text``.
* **Boundaries**: a chunk never spans two worksheets. Table / worksheet rows are never split
  unless a single row alone exceeds ``max_chars``. A heading is kept with the text below it
  (``max_chars`` is exceeded only by the length of such a carried heading, and only for
  headings up to a quarter of ``max_chars``).
* An oversized segment (typically a long PDF page) is split at the best available boundary
  (blank line, line break, sentence end, space, and finally a hard cut); every piece keeps the
  segment's page number and ``location_ref``.

Chunks carry no instructions. :meth:`Chunk.to_prompt_text` fences a chunk as *untrusted
data* for a later model call. That fencing, like text sanitising, is a mitigation and **not**
a defence against prompt injection: the reliable defences belong in the AI layer (no tools or
side effects for extraction calls, strict structured output, quotation verification against
the source, human confirmation before anything is trusted).
"""
from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from typing import Optional

from app.services.ingestion.sanitizer import ExtractedDocument, SegmentKind, TextSegment

__all__ = ["DEFAULT_MAX_CHARS", "MIN_MAX_CHARS", "Chunk", "ChunkSource", "chunk_document"]

DEFAULT_MAX_CHARS = 2_000
MIN_MAX_CHARS = 100

_ROW_KINDS = (SegmentKind.ROW, SegmentKind.TABLE_ROW)
_BREAKS = ("\n\n", "\n", ". ", "; ", ", ", " ")


@dataclass(frozen=True)
class ChunkSource:
    """Where one piece of a chunk's text came from."""

    segment_index: int  # index into ExtractedDocument.segments
    chunk_start: int  # span inside Chunk.text
    chunk_end: int
    segment_start: int  # span inside segments[segment_index].text
    segment_end: int
    kind: SegmentKind
    page_number: Optional[int] = None
    location_ref: Optional[str] = None
    sheet_name: Optional[str] = None


@dataclass(frozen=True)
class Chunk:
    index: int  # 0-based position in document order
    text: str
    source_filename: str
    file_type: str
    sources: tuple[ChunkSource, ...]
    #: Text of the nearest heading at or before the start of the chunk (None if there is none).
    heading: Optional[str] = None

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def page_start(self) -> Optional[int]:
        pages = [s.page_number for s in self.sources if s.page_number is not None]
        return min(pages) if pages else None

    @property
    def page_end(self) -> Optional[int]:
        pages = [s.page_number for s in self.sources if s.page_number is not None]
        return max(pages) if pages else None

    @property
    def sheet_name(self) -> Optional[str]:
        """The worksheet this chunk belongs to (a chunk never spans two)."""
        return next((s.sheet_name for s in self.sources if s.sheet_name is not None), None)

    @property
    def segment_indexes(self) -> tuple[int, ...]:
        seen: list[int] = []
        for source in self.sources:
            if source.segment_index not in seen:
                seen.append(source.segment_index)
        return tuple(seen)

    @property
    def location_ref(self) -> Optional[str]:
        """Short citation for the whole chunk: ``"page 3"``, ``"pages 3-5"``,
        ``"Sheet BOQ!A14:D14 to Sheet BOQ!A40:D40"`` ..."""
        if self.page_start is not None:
            if self.page_start == self.page_end:
                return f"page {self.page_start}"
            return f"pages {self.page_start}-{self.page_end}"
        refs = [s.location_ref for s in self.sources if s.location_ref]
        if not refs:
            return None
        unique = list(dict.fromkeys(refs))
        return unique[0] if len(unique) == 1 else f"{unique[0]} to {unique[-1]}"

    def locate(self, offset: int) -> Optional[ChunkSource]:
        """The source piece containing character ``offset`` of ``self.text``."""
        for source in self.sources:
            if source.chunk_start <= offset < source.chunk_end:
                return source
        return None

    def to_prompt_text(self, nonce: Optional[str] = None) -> str:
        """Render the chunk fenced as untrusted data, with its source for citation.

        The fence carries a random nonce that does not occur in the content, so the text
        cannot forge the closing marker. This does not stop a model from following
        instructions it reads inside the fence; see the module docstring.
        """
        source = json.dumps(self.source_filename, ensure_ascii=True)
        location = json.dumps(self.location_ref, ensure_ascii=True)
        haystack = f"{self.text}{source}{location}"
        if nonce is None:
            nonce = secrets.token_hex(8)
            while nonce in haystack:
                nonce = secrets.token_hex(8)
        elif nonce in haystack:
            raise ValueError("nonce occurs in the chunk content")
        return (
            f"<<<BEGIN UNTRUSTED DOCUMENT EXCERPT {nonce} source={source} location={location}>>>\n"
            f"{self.text}\n"
            f"<<<END UNTRUSTED DOCUMENT EXCERPT {nonce}>>>"
        )


@dataclass(frozen=True)
class _Unit:
    segment_index: int
    segment: TextSegment
    start: int
    end: int

    @property
    def text(self) -> str:
        return self.segment.text[self.start : self.end]

    @property
    def kind(self) -> SegmentKind:
        return self.segment.kind


def _separator(previous: SegmentKind, current: SegmentKind) -> str:
    """Same rule as ``ExtractedDocument.full_text``."""
    return "\n" if current in _ROW_KINDS and previous == current else "\n\n"


def _trim(text: str, start: int, end: int) -> Optional[tuple[int, int]]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if end > start else None


def _split_spans(text: str, limit: int) -> list[tuple[int, int]]:
    """Spans (start, end) of ``text``, each at most ``limit`` long, cut at the best boundary."""
    spans: list[tuple[int, int]] = []
    position = 0
    length = len(text)
    while position < length:
        if length - position <= limit:
            cut = length
        else:
            window_end = position + limit
            floor = position + limit // 2  # avoid cutting very early just to hit a nicer boundary
            cut = window_end
            for separator in _BREAKS:
                found = text.rfind(separator, floor, window_end)
                if found != -1:
                    # keep sentence punctuation with its sentence; break whitespace is trimmed
                    cut = found + (1 if separator in (". ", "; ", ", ") else len(separator))
                    break
        span = _trim(text, position, cut)
        if span:
            spans.append(span)
        position = cut
    return spans


def _units(document: ExtractedDocument, max_chars: int) -> list[_Unit]:
    units: list[_Unit] = []
    for index, segment in enumerate(document.segments):
        if not segment.text:
            continue
        if len(segment.text) <= max_chars:
            units.append(_Unit(index, segment, 0, len(segment.text)))
        else:
            units.extend(_Unit(index, segment, a, b) for a, b in _split_spans(segment.text, max_chars))
    return units


def _build(index: int, units: list[_Unit], document: ExtractedDocument, heading: Optional[str]) -> Chunk:
    parts: list[str] = []
    sources: list[ChunkSource] = []
    position = 0
    previous: Optional[SegmentKind] = None
    for unit in units:
        if previous is not None:
            separator = _separator(previous, unit.kind)
            parts.append(separator)
            position += len(separator)
        text = unit.text
        segment = unit.segment
        sources.append(
            ChunkSource(
                segment_index=unit.segment_index,
                chunk_start=position,
                chunk_end=position + len(text),
                segment_start=unit.start,
                segment_end=unit.end,
                kind=segment.kind,
                page_number=segment.page_number,
                location_ref=segment.location_ref,
                sheet_name=segment.sheet_name,
            )
        )
        parts.append(text)
        position += len(text)
        previous = unit.kind
    return Chunk(
        index=index,
        text="".join(parts),
        source_filename=document.filename,
        file_type=document.file_type,
        sources=tuple(sources),
        heading=heading,
    )


def chunk_document(document: ExtractedDocument, *, max_chars: int = DEFAULT_MAX_CHARS) -> list[Chunk]:
    """Split ``document`` into chunks of at most about ``max_chars`` characters.

    Returns ``[]`` for a document without text. Raises ``ValueError`` for a ``max_chars``
    below ``MIN_MAX_CHARS``.
    """
    if max_chars < MIN_MAX_CHARS:
        raise ValueError(f"max_chars must be at least {MIN_MAX_CHARS}")

    chunks: list[Chunk] = []
    current: list[_Unit] = []
    length = 0
    last_heading: Optional[str] = None
    chunk_heading: Optional[str] = None

    def flush() -> Optional[_Unit]:
        """Emit the current chunk; return a trailing heading to carry into the next one."""
        nonlocal current, length
        carry: Optional[_Unit] = None
        if len(current) > 1 and current[-1].kind is SegmentKind.HEADING and len(current[-1].text) <= max_chars // 4:
            carry = current.pop()
        chunks.append(_build(len(chunks), current, document, chunk_heading))
        current, length = [], 0
        return carry

    def add(unit: _Unit) -> None:
        nonlocal length, last_heading, chunk_heading
        if current:
            length += len(_separator(current[-1].kind, unit.kind))
        else:
            chunk_heading = unit.text if unit.kind is SegmentKind.HEADING else last_heading
        current.append(unit)
        length += len(unit.text)
        if unit.kind is SegmentKind.HEADING:
            last_heading = unit.text

    for unit in _units(document, max_chars):
        if current:
            previous = current[-1]
            new_sheet = unit.segment.sheet_name != previous.segment.sheet_name
            too_long = length + len(_separator(previous.kind, unit.kind)) + len(unit.text) > max_chars
            if new_sheet or too_long:
                carried = flush()
                if carried is not None and not new_sheet:
                    add(carried)
        add(unit)
    if current:
        flush()
    return chunks