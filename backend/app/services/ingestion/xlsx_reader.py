"""Excel (``.xlsx``) and delimited-text (``.csv`` / ``.tsv``) reader.

Both formats return the same shape: one ``SegmentKind.ROW`` segment per non-empty row.

* ``cells`` is column-aligned from the first column (``cells[0]`` is column A) with trailing
  blanks trimmed and blank cells as ``""``; it is authoritative for structure.
* ``text`` is the cells joined with ``" | "``, starting at the first non-empty cell
  (display only).
* ``location_ref``: ``"Sheet BOQ!A14:D14"`` for Excel (the range spans column A to the
  last non-empty cell) and ``"row 14"`` for CSV (a record number; quoted fields may span
  several physical lines).
* Excel segments also carry ``sheet_name``.

Worksheets
----------
Visible worksheets are read. Hidden / very-hidden sheets are skipped with a warning (pass
``include_hidden=True`` to read them); chart sheets have no cells. Sheets without data are
listed in ``metadata["empty_sheets"]``.

Formulas are **never evaluated**. The reader returns the value Excel last cached in the file.
A formula with no cached value (a workbook produced by a script and never opened in Excel)
shows as an empty cell, is counted in ``metadata["uncached_formula_cells"]`` and listed in a
warning, so it cannot be mistaken for a real blank. If the workbook has content only in such
cells the status is ``NO_EXTRACTABLE_TEXT``. Number formats are not applied: a cell shown as
``15%`` in Excel is returned as ``0.15``. Merged cells carry their value in the top-left cell
only. Error values (``#DIV/0!`` ...) are kept as text and counted.

Safety (the file is untrusted): size and extension are checked by ``load_source``; the zip
container by ``ensure_ooxml``; a workbook carrying a VBA project is refused; external links
are not loaded (``keep_links=False``); sheets are streamed (``read_only``) and the declared
sheet dimensions are ignored, so a crafted ``A1:XFD1048576`` cannot inflate memory; rows and
non-empty cells are capped. ``defusedxml`` (see requirements) makes openpyxl's streaming
parser (sheet data and shared strings, the large parts) reject XML entity declarations; the
small workbook-level parts are parsed by lxml with entity resolution switched off. Sanitising is applied but is *not* a defence against prompt
injection: instructions written in a cell are returned verbatim, as text. Cell values that
start with ``=``, ``+``, ``-`` or ``@`` are plain data here; escape them before any future
export to CSV/Excel.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import math
import zipfile
from decimal import Decimal
from typing import Any, Optional

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from app.services.ingestion.sanitizer import (
    MAX_FILE_BYTES,
    CorruptDocumentError,
    ExtractedDocument,
    ExtractionStatus,
    IngestionError,
    ResourceLimitError,
    SanitizationReport,
    SegmentKind,
    Source,
    TextSegment,
    UnsupportedFormatError,
    ensure_ooxml,
    load_source,
    sanitize_text_with_report,
)
from app.services.ingestion.text_reader import _decode

__all__ = ["MAX_CELLS", "MAX_ROWS", "XLSX_EXTENSIONS", "CSV_EXTENSIONS", "read_xlsx", "read_csv"]

MAX_CELLS = 5_000_000  # non-empty cells across the whole file
MAX_ROWS = 1_048_576  # Excel's own row limit, applied per sheet / per CSV file
XLSX_EXTENSIONS = (".xlsx",)
CSV_EXTENSIONS = (".csv", ".tsv")

_MAX_REFS_IN_MESSAGE = 10
_EXCEL_ERRORS = frozenset(
    {"#NULL!", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#N/A", "#GETTING_DATA"}
)
_CSV_SNIFF_CHARS = 8192
_CSV_DELIMITERS = ",;\t|"


class _Tally:
    """Shared cleaning + limits so Excel and CSV behave the same."""

    def __init__(self) -> None:
        self.report = SanitizationReport()
        self.cells = 0

    def clean(self, raw: str) -> str:
        text, part = sanitize_text_with_report(raw)
        self.report.merge(part)
        return " ".join(text.split())  # a cell is one line; the column structure is in `cells`

    def count_cell(self) -> None:
        self.cells += 1
        if self.cells > MAX_CELLS:
            raise ResourceLimitError(f"The file has more than {MAX_CELLS} non-empty cells.")


def _format_float(value: float) -> str:
    if not math.isfinite(value):
        return str(value)
    text = format(Decimal(repr(value)), "f")  # no scientific notation
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "-0" if text == "-0" else text


def _format_value(value: Any, tally: _Tally) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _format_float(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dt.datetime):
        if value.time() == dt.time(0):
            return value.date().isoformat()
        return value.isoformat(sep=" ")
    if isinstance(value, (dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return str(value)
    return tally.clean(str(value))


def _row_segment(
    cells: list[str], name: str, location_ref: str, sheet_name: Optional[str]
) -> Optional[TextSegment]:
    while cells and not cells[-1]:
        cells.pop()
    if not cells:
        return None
    first = next(i for i, c in enumerate(cells) if c)
    return TextSegment(
        text=" | ".join(cells[first:]),
        kind=SegmentKind.ROW,
        source_filename=name,
        location_ref=location_ref,
        sheet_name=sheet_name,
        cells=tuple(cells),
    )


def _ref_list(refs: list[str], total: int) -> str:
    shown = ", ".join(refs[:_MAX_REFS_IN_MESSAGE])
    extra = total - min(len(refs), _MAX_REFS_IN_MESSAGE)
    return f"{shown} (and {extra} more)" if extra > 0 else shown


def _name_list(names: list[str]) -> str:
    return ", ".join(repr(n) for n in names)


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------
def _open_workbooks(data: bytes):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if any(n.lower().endswith("vbaproject.bin") for n in archive.namelist()):
                raise UnsupportedFormatError(
                    "The workbook contains a VBA macro project; macro-enabled files are not accepted."
                )
        values = load_workbook(io.BytesIO(data), read_only=True, data_only=True, keep_links=False)
        formulas = load_workbook(io.BytesIO(data), read_only=True, data_only=False, keep_links=False)
        return values, formulas
    except IngestionError:
        raise
    except MemoryError as exc:
        raise ResourceLimitError("The workbook needs more memory to open than is allowed.") from exc
    except Exception as exc:  # noqa: BLE001 - openpyxl/defusedxml raise many types on hostile input
        raise CorruptDocumentError(
            f"The XLSX file is corrupt or could not be parsed ({type(exc).__name__})."
        ) from exc


def read_xlsx(
    source: Source,
    filename: Optional[str] = None,
    *,
    include_hidden: bool = False,
    max_bytes: int = MAX_FILE_BYTES,
) -> ExtractedDocument:
    """Extract every non-empty row of every visible worksheet.

    Raises :class:`IngestionError` subclasses (``UnsupportedFormatError``,
    ``CorruptDocumentError``, ``ResourceLimitError``); never returns an "error result".
    """
    data, name = load_source(source, filename, XLSX_EXTENSIONS, max_bytes)
    ensure_ooxml(data, "xl/workbook.xml", "XLSX")
    wb_values, wb_formulas = _open_workbooks(data)

    tally = _Tally()
    segments: list[TextSegment] = []
    sheets_read: list[str] = []
    empty_sheets: list[str] = []
    skipped_hidden: list[str] = []
    formula_cells = 0
    uncached_total = 0
    uncached_refs: list[str] = []
    error_cells = 0

    try:
        for ws_values in wb_values.worksheets:
            title = ws_values.title
            if ws_values.sheet_state != "visible" and not include_hidden:
                skipped_hidden.append(title)
                continue
            ws_formulas = wb_formulas[title]
            # Ignore the dimensions the file claims: they are attacker-controlled.
            ws_values.reset_dimensions()
            ws_formulas.reset_dimensions()

            sheets_read.append(title)
            before = len(segments)
            for row_number, (values, formula_row) in enumerate(
                zip(ws_values.iter_rows(values_only=True), ws_formulas.iter_rows()), start=1
            ):
                if row_number > MAX_ROWS:
                    raise ResourceLimitError(f"Sheet {title!r} has more than {MAX_ROWS} rows.")
                cells: list[str] = []
                for index, value in enumerate(values):
                    cell = formula_row[index] if index < len(formula_row) else None
                    if getattr(cell, "data_type", None) == "f":
                        formula_cells += 1
                        if value is None:
                            uncached_total += 1
                            if len(uncached_refs) < _MAX_REFS_IN_MESSAGE:
                                uncached_refs.append(f"{title}!{get_column_letter(index + 1)}{row_number}")
                    if isinstance(value, str) and value in _EXCEL_ERRORS:
                        error_cells += 1
                    text = _format_value(value, tally)
                    if text:
                        tally.count_cell()
                    cells.append(text)
                while cells and not cells[-1]:
                    cells.pop()
                last = len(cells)
                ref = (
                    f"Sheet {title}!A{row_number}"
                    if last == 1
                    else f"Sheet {title}!A{row_number}:{get_column_letter(max(last, 1))}{row_number}"
                )
                segment = _row_segment(cells, name, ref, title)
                if segment is not None:
                    segments.append(segment)
            if len(segments) == before:
                empty_sheets.append(title)
    except IngestionError:
        raise
    except MemoryError as exc:
        raise ResourceLimitError("The workbook needs more memory to read than is allowed.") from exc
    except Exception as exc:  # noqa: BLE001 - malformed sheet XML can fail in many ways
        raise CorruptDocumentError(
            f"The XLSX content could not be read ({type(exc).__name__})."
        ) from exc
    finally:
        wb_values.close()
        wb_formulas.close()

    warnings = tally.report.warnings()
    if skipped_hidden:
        warnings.append(
            f"Hidden sheet(s) {_name_list(skipped_hidden)} were skipped. "
            "Their content is not in the extracted text."
        )
    if empty_sheets:
        warnings.append(f"Sheet(s) {_name_list(empty_sheets)} contain no data.")
    if uncached_total:
        warnings.append(
            f"{uncached_total} formula cell(s) have no cached value (the workbook was never "
            f"calculated in Excel), so they appear empty: {_ref_list(uncached_refs, uncached_total)}. "
            "Formulas are not evaluated."
        )
    if error_cells:
        warnings.append(f"{error_cells} cell(s) contain Excel error values (such as #DIV/0!).")

    if segments:
        status = ExtractionStatus.OK
    elif uncached_total:
        status = ExtractionStatus.NO_EXTRACTABLE_TEXT
    else:
        status = ExtractionStatus.EMPTY
        if not sheets_read and not skipped_hidden:
            warnings.append("The workbook has no worksheets.")

    return ExtractedDocument(
        filename=name,
        file_type="xlsx",
        status=status,
        segments=segments,
        page_count=None,
        warnings=warnings,
        metadata={
            "sheets_read": sheets_read,
            "empty_sheets": empty_sheets,
            "hidden_sheets_skipped": skipped_hidden,
            "formula_cells": formula_cells,
            "uncached_formula_cells": uncached_total,
            "error_cells": error_cells,
            "formulas_evaluated": False,
            "values_source": "cached_values",
            "sanitization": tally.report.as_dict(),
        },
    )


# ---------------------------------------------------------------------------
# CSV / TSV
# ---------------------------------------------------------------------------
def _pick_delimiter(text: str, forced: Optional[str], is_tsv: bool) -> str:
    if forced:
        if len(forced) != 1:
            raise ValueError("delimiter must be a single character")
        return forced
    if is_tsv:
        return "\t"
    try:
        return csv.Sniffer().sniff(text[:_CSV_SNIFF_CHARS], delimiters=_CSV_DELIMITERS).delimiter
    except csv.Error:
        return ","


def read_csv(
    source: Source,
    filename: Optional[str] = None,
    *,
    encoding: Optional[str] = None,
    delimiter: Optional[str] = None,
    max_bytes: int = MAX_FILE_BYTES,
) -> ExtractedDocument:
    """Extract every non-empty record of a ``.csv`` / ``.tsv`` file.

    Encoding is never guessed (same rules as :func:`read_text`). The delimiter is sniffed
    from ``, ; TAB |`` unless given (``.tsv`` always uses a tab) and is recorded in
    ``metadata["delimiter"]``. Raises :class:`IngestionError` subclasses.
    """
    data, name = load_source(source, filename, CSV_EXTENSIONS, max_bytes)
    if not data:
        raise CorruptDocumentError("The CSV file is empty (0 bytes).")
    text, used_encoding = _decode(data, encoding, name)
    is_tsv = name.lower().endswith(".tsv")

    tally = _Tally()
    nul_count = text.count("\x00")
    if nul_count:  # the csv module rejects NUL on older Pythons; count it so it is reported
        text = text.replace("\x00", "")
        tally.report.null_bytes_removed += nul_count

    used_delimiter = _pick_delimiter(text, delimiter, is_tsv)
    segments: list[TextSegment] = []
    record_count = 0
    max_columns = 0
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=used_delimiter)
    try:
        for record_count, row in enumerate(reader, start=1):
            if record_count > MAX_ROWS:
                raise ResourceLimitError(f"The file has more than {MAX_ROWS} rows.")
            cells = [tally.clean(value) for value in row]
            for cell in cells:
                if cell:
                    tally.count_cell()
            segment = _row_segment(cells, name, f"row {record_count}", None)
            if segment is not None:
                max_columns = max(max_columns, len(segment.cells or ()))
                segments.append(segment)
    except csv.Error as exc:
        raise CorruptDocumentError(
            f"The CSV could not be parsed near record {reader.line_num}: {exc}"
        ) from exc

    return ExtractedDocument(
        filename=name,
        file_type="tsv" if is_tsv else "csv",
        status=ExtractionStatus.OK if segments else ExtractionStatus.EMPTY,
        segments=segments,
        page_count=None,
        warnings=tally.report.warnings(),
        metadata={
            "encoding": used_encoding,
            "delimiter": used_delimiter,
            "record_count": record_count,
            "max_columns": max_columns,
            "sanitization": tally.report.as_dict(),
        },
    )