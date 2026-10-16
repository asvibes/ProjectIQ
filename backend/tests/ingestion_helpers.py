"""Builders for the small sample files used by the ingestion tests (no binary fixtures)."""
from __future__ import annotations

import io
import re
import zipfile
from typing import Callable, Optional, Sequence

import docx
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from openpyxl import Workbook


def make_pdf(pages: Sequence[Optional[str]]) -> bytes:
    """A minimal valid PDF. Each item is that page's text (``\\n`` = new line) or ``None`` for
    a page with no text layer (what a scanned page looks like to a text extractor)."""
    count = len(pages)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(count))
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, text in enumerate(pages):
        if text is None:
            content = b""
        else:
            lines = [
                "(" + line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj"
                for line in text.split("\n")
            ]
            content = ("BT /F1 12 Tf 14 TL 72 720 Td " + " T* ".join(lines) + " ET").encode("latin-1")
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>"
            ).encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1) + b"0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref_at)
    return bytes(out)


def docx_bytes(build: Callable[["docx.document.Document"], None]) -> bytes:
    document = docx.Document()
    build(document)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def add_raw_xml(paragraph, xml: str) -> None:
    """Append raw WordprocessingML to a paragraph. Put ``{NS}`` inside the root start tag."""
    paragraph._p.append(parse_xml(xml.replace("{NS}", nsdecls("w"))))


def rewrite_zip(data: bytes, replace: Optional[dict[str, bytes]] = None, add: Optional[dict[str, bytes]] = None) -> bytes:
    """Copy a zip, replacing / adding members (used to inject hostile parts)."""
    source = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if replace and info.filename in replace:
                payload = replace[info.filename]
            target.writestr(info.filename, payload)
        for name, payload in (add or {}).items():
            target.writestr(name, payload)
    return out.getvalue()


def xlsx_bytes(build: Callable[[Workbook], None]) -> bytes:
    workbook = Workbook()
    build(workbook)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def patch_sheet_xml(data: bytes, pattern: str, replacement: str, sheet: str = "xl/worksheets/sheet1.xml") -> bytes:
    xml = zipfile.ZipFile(io.BytesIO(data)).read(sheet).decode("utf-8")
    patched, count = re.subn(pattern, replacement, xml)
    assert count, f"pattern {pattern!r} not found in {sheet}: {xml[:400]}"
    return rewrite_zip(data, replace={sheet: patched.encode("utf-8")})