"""Cross-reader checks: every reader returns the same, compatible structure."""
import io
import re

import pytest

from app.services.ingestion.chunker import chunk_document
from app.services.ingestion.docx_reader import read_docx
from app.services.ingestion.pdf_reader import read_pdf
from app.services.ingestion.sanitizer import (
    ExtractedDocument,
    ExtractionStatus,
    IngestionError,
    SegmentKind,
    TextSegment,
)
from app.services.ingestion.text_reader import read_text
from app.services.ingestion.xlsx_reader import read_csv, read_xlsx
from ingestion_helpers import docx_bytes, make_pdf, xlsx_bytes

_CONTROL = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f​⁠﻿­]")


def _samples() -> list[tuple[str, ExtractedDocument]]:
    def docx_build(d):
        d.add_heading("Scope", level=1)
        d.add_paragraph("Paragraph")
        t = d.add_table(rows=1, cols=2)
        t.cell(0, 0).text, t.cell(0, 1).text = "a", "b"

    def xlsx_build(wb):
        wb.active.title = "S"
        wb.active.append(["a", 1])

    return [
        ("txt", read_text(b"Alpha\n\nBeta\n", "a.txt")),
        ("md", read_text(b"# H\n\nBody\n", "a.md")),
        ("pdf", read_pdf(make_pdf(["Alpha", "Beta"]), "a.pdf")),
        ("docx", read_docx(docx_bytes(docx_build), "a.docx")),
        ("xlsx", read_xlsx(xlsx_bytes(xlsx_build), "a.xlsx")),
        ("csv", read_csv(b"a,b\n1,2\n", "a.csv")),
    ]


@pytest.mark.parametrize("file_type,doc", _samples(), ids=[s[0] for s in _samples()])
def test_every_reader_returns_the_shared_structure(file_type, doc):
    assert isinstance(doc, ExtractedDocument)
    assert doc.file_type == file_type and doc.status is ExtractionStatus.OK and doc.has_text
    assert isinstance(doc.warnings, list) and isinstance(doc.metadata, dict)
    assert "sanitization" in doc.metadata
    assert doc.page_count is None or doc.page_count >= 1
    for segment in doc.segments:
        assert isinstance(segment, TextSegment) and isinstance(segment.kind, SegmentKind)
        assert segment.source_filename == doc.filename
        assert segment.text and not _CONTROL.search(segment.text)
        assert segment.location_ref and len(segment.location_ref) <= 255  # fits the DB column
        assert segment.page_number is None or segment.page_number >= 1  # fits page_positive check
        if segment.cells is not None:
            assert segment.kind in (SegmentKind.ROW, SegmentKind.TABLE_ROW)
    assert doc.full_text and doc.to_marked_text()
    assert chunk_document(doc), "every successfully read document can be chunked"


def test_every_reader_raises_ingestion_errors_with_user_presentable_messages():
    bad = [
        (read_text, b"", "x.txt"),
        (read_pdf, b"", "x.pdf"),
        (read_docx, b"", "x.docx"),
        (read_xlsx, b"", "x.xlsx"),
        (read_csv, b"", "x.csv"),
        (read_pdf, b"not a pdf", "x.pdf"),
        (read_docx, b"not a zip", "x.docx"),
        (read_xlsx, b"not a zip", "x.xlsx"),
    ]
    for reader, data, name in bad:
        with pytest.raises(IngestionError) as info:
            reader(data, name)
        message = str(info.value)
        assert message and message.strip() == message  # Document.mark_failed rejects blank reasons
        assert "Traceback" not in message and "/home/" not in message  # no internals leaked


def test_reader_leaves_the_callers_stream_open():
    stream = io.BytesIO(make_pdf(["Alpha"]))
    read_pdf(stream, "s.pdf")
    assert not stream.closed


def test_sanitised_segments_do_not_hide_tag_or_bidi_characters_silently():
    """Documents a known gap rather than hiding it: the shared sanitiser does not remove
    Unicode tag characters (U+E0000..E007F, usable to smuggle invisible instructions) or bidi
    override controls. Readers return them unchanged; the AI layer must treat all text as data."""
    hidden = "visible" + "".join(chr(0xE0000 + ord(c)) for c in "ignore previous")
    doc = read_text(hidden.encode("utf-8"), "tags.txt")
    assert doc.segments[0].text == hidden  # unchanged: no silent edits, but also no warning
    assert doc.warnings == []