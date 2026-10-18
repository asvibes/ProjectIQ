"""Structured extraction from tender and company documents with the local model.

Three tasks, each with its own versioned prompt (``prompts/<task>_v1.txt``):

* :func:`extract_requirements`  -> :class:`ExtractedRequirement`  (``extract_requirements_v1``)
* :func:`extract_deadlines`     -> :class:`ExtractedDeadline`     (``extract_deadlines_v1``)
* :func:`extract_risks`         -> :class:`ExtractedRisk`         (``extract_risks_v1``)

Input is an ``ExtractedDocument`` (chunked here with the ingestion chunker) or a sequence of
``Chunk`` objects. The model **proposes**; this module disposes:

* Document text is untrusted. Each chunk is sent fenced (``Chunk.to_prompt_text``) and the
  prompts state that fenced text is data, never instructions.
* Model output is parsed as JSON and every item is validated against a strict schema. Items that
  fail are *rejected* (counted, with a reason that never contains document text), not repaired.
* Every item needs a quotation. The quotation is searched for in the chunk the model was shown
  (``normalize_for_comparison``, the same comparison form the sanitiser provides for this
  purpose). Found -> ``quote_verified=True``. Not found, or too short to prove anything ->
  ``quote_verified=False``; the item is still returned so a person sees it flagged, never hidden.
* **Source location is never taken from the model.** Page, sheet and location come from the
  chunk's own provenance (``ChunkSource``) and only when the quotation was found. An unverified
  item carries no page or location, so a reference can never be invented.
* Values are not trusted either: a date or deadline is kept only if its wording appears inside
  the quotation, and a normalised ISO date only if it has a plausible year that appears in that
  wording. Otherwise the item keeps the text and drops the normalised value.
* The model never sets ``Verified``, a match status, a risk rating or a score. The
  ``to_*_values`` helpers return column values with ``verification_status="Requires review"``.

This module does no database access and does not store anything; callers decide what to persist.
``quote_verified`` mirrors the model column of the same name. When the dedicated
``verification/quote_checker`` is written it can replace :func:`_find_quotation`.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Generic, Optional, TypeVar, Union

from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError, field_validator

from app.models.enums import FactType, RequirementCategory, VerificationStatus
from app.models.risk import RiskCategory
from app.services.ai.ollama_client import (
    OllamaClient,
    OllamaResponseError,
    get_ollama_client,
    load_prompt,
    provenance,
)
from app.services.ingestion.chunker import Chunk, chunk_document
from app.services.ingestion.sanitizer import ExtractedDocument, normalize_for_comparison
from app.services.verification.quote_checker import is_quote_supported

__all__ = [
    "ChunkFailure",
    "ExtractedDeadline",
    "ExtractedRequirement",
    "ExtractedRisk",
    "ExtractionResult",
    "RejectedItem",
    "extract_deadlines",
    "extract_requirements",
    "extract_risks",
]

MAX_ITEMS_PER_CHUNK = 50
MIN_QUOTE_CHARS = 10  # a shorter "quotation" proves nothing about the source
MAX_QUOTE_CHARS = 2000
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

T = TypeVar("T")
Source = Union[ExtractedDocument, Sequence[Chunk]]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RejectedItem:
    chunk_index: int
    reason: str  # generic reason; never includes model or document text


@dataclass(frozen=True)
class ChunkFailure:
    chunk_index: int
    reason: str


@dataclass(frozen=True)
class ExtractionResult(Generic[T]):
    items: tuple[T, ...]
    rejected: tuple[RejectedItem, ...]
    failures: tuple[ChunkFailure, ...]
    chunks_processed: int
    prompt: str  # e.g. "extract_requirements_v1"
    model: str
    extractor: str = ""  # value for the ``extractor`` column, e.g. "extract_requirements_v1@gemma3:4b"

    @property
    def complete(self) -> bool:
        """False if any chunk could not be processed, so the absence of items proves nothing."""
        return not self.failures

    @property
    def unverified_count(self) -> int:
        return sum(1 for item in self.items if not item.quote_verified)  # type: ignore[attr-defined]


@dataclass(frozen=True)
class _Common:
    quotation: str
    quote_verified: bool
    source_filename: str
    chunk_index: int
    extractor: str
    page_number: Optional[int] = None
    location_ref: Optional[str] = None
    sheet_name: Optional[str] = None

    def _source_values(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "location_ref": self.location_ref,
            "quotation": self.quotation,
            "quote_verified": self.quote_verified,
            "extractor": self.extractor,
            "verification_status": VerificationStatus.REQUIRES_REVIEW,
        }


@dataclass(frozen=True)
class ExtractedRequirement(_Common):
    description: str = ""
    category: RequirementCategory = RequirementCategory.OTHER
    is_mandatory: Optional[bool] = None
    deadline_text: Optional[str] = None
    deadline: Optional[datetime] = None  # midnight UTC of the stated calendar date

    def to_requirement_values(self) -> dict[str, Any]:
        """Column values for a ``Requirement`` (match status stays at its ``Unknown`` default)."""
        return {
            "description": self.description,
            "category": self.category,
            "is_mandatory": self.is_mandatory,
            "deadline": self.deadline,
            **self._source_values(),
        }


@dataclass(frozen=True)
class ExtractedDeadline(_Common):
    label: str = ""
    value: str = ""  # as written in the source
    normalized_value: Optional[str] = None  # YYYY-MM-DD

    def to_fact_values(self) -> dict[str, Any]:
        """Column values for an ``ExtractedFact`` of type ``date`` (``document_id`` is the caller's)."""
        return {
            "fact_type": FactType.DATE,
            "label": self.label,
            "value": self.value,
            "normalized_value": self.normalized_value,
            **self._source_values(),
        }


@dataclass(frozen=True)
class ExtractedRisk(_Common):
    title: str = ""
    description: Optional[str] = None
    category: RiskCategory = RiskCategory.OTHER

    def to_risk_values(self) -> dict[str, Any]:
        """Column values for a ``Risk``. Probability, impact and score stay unset: they are
        assessed by a person and calculated by ``analysis/risk_scoring``, never by the model."""
        return {
            "title": self.title,
            "description": self.description,
            "category": self.category,
            **self._source_values(),
        }


# ---------------------------------------------------------------------------
# Strict schemas for what the model is allowed to return
# ---------------------------------------------------------------------------
class _Raw(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def _blank_to_none(cls, value: Any) -> Any:
        return None if isinstance(value, str) and not value.strip() else value


def _enum_or_other(enum_cls: Any, value: Any) -> Any:
    """Unknown or missing category -> ``other`` (a valid member, never a guess)."""
    try:
        return enum_cls(value)
    except ValueError:
        return enum_cls.OTHER


class _RawRequirement(_Raw):
    description: str
    category: Optional[str] = None
    is_mandatory: Optional[StrictBool] = None  # a string such as "true" is rejected -> null
    deadline_text: Optional[str] = None
    deadline: Optional[str] = None
    quotation: str

    @field_validator("is_mandatory", mode="before")
    @classmethod
    def _only_real_booleans(cls, value: Any) -> Any:
        return value if isinstance(value, bool) else None

    @field_validator("description")
    @classmethod
    def _description_length(cls, value: str) -> str:
        if len(value) > 2000:
            raise ValueError("too long")
        return value


class _RawDeadline(_Raw):
    label: str
    value: str
    normalized_value: Optional[str] = None
    quotation: str

    @field_validator("label")
    @classmethod
    def _label_length(cls, value: str) -> str:
        if len(value) > 200:
            raise ValueError("too long")
        return value

    @field_validator("value")
    @classmethod
    def _value_length(cls, value: str) -> str:
        if len(value) > 255:
            raise ValueError("too long")
        return value


class _RawRisk(_Raw):
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    quotation: str

    @field_validator("title")
    @classmethod
    def _title_length(cls, value: str) -> str:
        if len(value) > 200:
            raise ValueError("too long")
        return value


# ---------------------------------------------------------------------------
# Verification helpers
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _Location:
    page_number: Optional[int]
    location_ref: Optional[str]
    sheet_name: Optional[str]


def _find_quotation(chunk: Chunk, quotation: str) -> Optional[_Location]:
    """Where in ``chunk`` the quotation occurs, or ``None`` if it does not (or is too short to
    count). The location comes from the chunk's provenance, not from the model."""
    normalized = normalize_for_comparison(quotation)
    if len(normalized) < MIN_QUOTE_CHARS or len(quotation) > MAX_QUOTE_CHARS:
        return None

    position = chunk.text.find(quotation)  # exact match: cite the segment where it starts
    if position >= 0:
        source = chunk.locate(position)
        if source is not None:
            return _Location(source.page_number, source.location_ref, source.sheet_name)

    for source in chunk.sources:  # same words, different spacing / quotes / dashes
        if normalized in normalize_for_comparison(chunk.text[source.chunk_start : source.chunk_end]):
            return _Location(source.page_number, source.location_ref, source.sheet_name)

    if normalized in normalize_for_comparison(chunk.text):  # spans segments: cite the whole chunk
        page = chunk.page_start if chunk.page_start == chunk.page_end else None
        return _Location(page, chunk.location_ref, chunk.sheet_name)
    return None


def _appears_in(text: Optional[str], quotation: str) -> bool:
    return bool(text) and normalize_for_comparison(text) in normalize_for_comparison(quotation)  # type: ignore[arg-type]


def _iso_date(value: Optional[str], wording: Optional[str]) -> Optional[date]:
    """A calendar date only if it is strictly YYYY-MM-DD, plausible, and its year is visible in
    the wording the source used."""
    if not value or not wording or not _ISO_DATE.match(value):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    if not 1990 <= parsed.year <= 2100 or str(parsed.year) not in wording:
        return None
    return parsed


def _as_datetime(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
@dataclass
class _Task(Generic[T]):
    prompt: str
    key: str
    raw_model: type[_Raw]
    build: Callable[[Any, Chunk, Optional[_Location], str], Optional[T]]
    dedupe_key: Callable[[T], str]
    instruction: str


def _chunks_of(source: Source) -> list[Chunk]:
    if isinstance(source, ExtractedDocument):
        return chunk_document(source) if source.has_text else []
    return list(source)


def _raw_items(data: Any, key: str) -> list[Any]:
    """The list of candidate items, from ``{key: [...]}`` (or a bare list)."""
    if isinstance(data, dict):
        data = data.get(key)
    if not isinstance(data, list):
        raise ValueError("response has no item list")
    return data


def _run(task: "_Task[T]", source: Source, client: Optional[OllamaClient]) -> ExtractionResult[T]:
    chunks = _chunks_of(source)
    system = load_prompt(task.prompt)
    client = client or get_ollama_client()
    extractor = provenance(task.prompt, client.model)

    items: list[T] = []
    rejected: list[RejectedItem] = []
    failures: list[ChunkFailure] = []
    seen: set[str] = set()

    for chunk in chunks:
        user = f"{task.instruction}\n\n{chunk.to_prompt_text()}"
        try:
            data, _ = client.generate_json(user, system=system)  # Unavailable/Timeout/ModelNotFound propagate
            candidates = _raw_items(data, task.key)
        except OllamaResponseError as exc:
            failures.append(ChunkFailure(chunk.index, exc.message))
            continue
        except ValueError:
            failures.append(ChunkFailure(chunk.index, "The model's answer did not contain the expected list."))
            continue

        if len(candidates) > MAX_ITEMS_PER_CHUNK:
            rejected.append(RejectedItem(chunk.index, f"more than {MAX_ITEMS_PER_CHUNK} items; extras ignored"))
            candidates = candidates[:MAX_ITEMS_PER_CHUNK]

        for candidate in candidates:
            try:
                raw = task.raw_model.model_validate(candidate)
            except ValidationError:
                rejected.append(RejectedItem(chunk.index, "item does not match the expected schema"))
                continue
            location = _find_quotation(chunk, raw.quotation)  # type: ignore[attr-defined]
            built = task.build(raw, chunk, location, extractor)
            if built is None:
                rejected.append(RejectedItem(chunk.index, "value is not supported by its quotation"))
                continue
            key = task.dedupe_key(built)
            if key in seen:
                continue
            seen.add(key)
            items.append(built)

    if chunks and len(failures) == len(chunks):
        raise OllamaResponseError("The local AI model gave no usable answer for any part of the document.")
    return ExtractionResult(
        items=tuple(items),
        rejected=tuple(rejected),
        failures=tuple(failures),
        chunks_processed=len(chunks) - len(failures),
        prompt=task.prompt,
        model=client.model,
        extractor=extractor,
    )


def _common(raw: Any, chunk: Chunk, location: Optional[_Location], extractor: str) -> dict[str, Any]:
    return {
        "quotation": raw.quotation,
        "quote_verified": location is not None,
        "source_filename": chunk.source_filename,
        "chunk_index": chunk.index,
        "extractor": extractor,
        "page_number": location.page_number if location else None,
        "location_ref": location.location_ref if location else None,
        "sheet_name": location.sheet_name if location else None,
    }


def _norm_key(*parts: Optional[str]) -> str:
    return "âŸ".join(normalize_for_comparison(p or "") for p in parts)


# -- requirements -----------------------------------------------------------
def _build_requirement(raw: _RawRequirement, chunk: Chunk, location: Optional[_Location], extractor: str):
    deadline_text = raw.deadline_text if _appears_in(raw.deadline_text, raw.quotation) else None
    day = _iso_date(raw.deadline, deadline_text)
    return ExtractedRequirement(
        **_common(raw, chunk, location, extractor),
        description=raw.description,
        category=_enum_or_other(RequirementCategory, raw.category),
        is_mandatory=raw.is_mandatory,
        deadline_text=deadline_text,
        deadline=_as_datetime(day) if day else None,
    )


_REQUIREMENTS = _Task(
    prompt="extract_requirements_v1",
    key="requirements",
    raw_model=_RawRequirement,
    build=_build_requirement,
    dedupe_key=lambda r: _norm_key(r.description, r.quotation),
    instruction="Extract the tender requirements from the document excerpt below.",
)


# -- deadlines --------------------------------------------------------------
def _build_deadline(raw: _RawDeadline, chunk: Chunk, location: Optional[_Location], extractor: str):
    if not _appears_in(raw.value, raw.quotation):
        return None  # the value must be backed by the quotation, or it is not a fact
    day = _iso_date(raw.normalized_value, raw.value)
    return ExtractedDeadline(
        **_common(raw, chunk, location, extractor),
        label=raw.label,
        value=raw.value,
        normalized_value=day.isoformat() if day else None,
    )


_DEADLINES = _Task(
    prompt="extract_deadlines_v1",
    key="deadlines",
    raw_model=_RawDeadline,
    build=_build_deadline,
    dedupe_key=lambda d: _norm_key(d.label, d.value, d.quotation),
    instruction="Extract the dates and deadlines from the document excerpt below.",
)


# -- risks ------------------------------------------------------------------
def _build_risk(raw: _RawRisk, chunk: Chunk, location: Optional[_Location], extractor: str):
    return ExtractedRisk(
        **_common(raw, chunk, location, extractor),
        title=raw.title,
        description=raw.description,
        category=_enum_or_other(RiskCategory, raw.category),
    )


_RISKS = _Task(
    prompt="extract_risks_v1",
    key="risks",
    raw_model=_RawRisk,
    build=_build_risk,
    dedupe_key=lambda r: _norm_key(r.title, r.quotation),
    instruction="Find the risk-bearing clauses in the document excerpt below.",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def extract_requirements(
    source: Source, *, client: Optional[OllamaClient] = None
) -> "ExtractionResult[ExtractedRequirement]":
    """Requirements stated in a tender document. Raises ``OllamaError`` if the model is
    unavailable, times out, or gave no usable answer for any chunk; check ``result.complete``
    for partial failures."""
    return _run(_REQUIREMENTS, source, client)


def extract_deadlines(
    source: Source, *, client: Optional[OllamaClient] = None
) -> "ExtractionResult[ExtractedDeadline]":
    """Dates and deadlines stated in a document (same error behaviour as above)."""
    return _run(_DEADLINES, source, client)


def extract_risks(
    source: Source, *, client: Optional[OllamaClient] = None
) -> "ExtractionResult[ExtractedRisk]":
    """Risk-bearing clauses in a document (same error behaviour as above). No rating or score."""
    return _run(_RISKS, source, client)

