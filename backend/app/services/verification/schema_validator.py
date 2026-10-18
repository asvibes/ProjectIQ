"""Strict validation of AI-extracted items before anything is stored (FR-13).

The extractor's output is *proposed* data. This module checks a proposed item against the
existing ORM models (``Requirement``, ``ExtractedFact``, ``Risk``) and the extraction contract
described in ``services/ai/extractor``, and reports every problem it finds. It never repairs,
guesses or fills in values: an item that fails is rejected, with reasons, so a person or a
caller can see why. Like the finance and analysis modules it is made of *pure functions*: no
database access, no clock, no randomness and no language model.

What is checked
---------------
Column rules are **read from the models**, not copied, so they cannot drift from the schema:
the column's type (enum members, whole numbers, true/false, timezone-aware datetimes, text),
its maximum length, and whether it is required (``NOT NULL`` with no default). Rules the model
holds as constraints or validators rather than column metadata are repeated here and named:

* ``page_number`` is 1 or greater (``SourceLocationMixin`` / ``page_positive``).
* An ``ExtractedFact`` needs a non-blank ``label``, ``value`` and ``quotation``
  (``value_not_blank`` / ``quotation_not_blank``); a ``Risk`` needs a non-blank ``title``
  (``title_not_blank``); a ``Requirement`` needs a non-blank ``description``.

The extraction contract (``services/ai/extractor`` module docstring) adds:

* **Only the columns an extractor fills.** Other real columns (match status, risk ratings,
  scores, notes, owner, ...) are ``not_permitted`` in extracted data; names that are not
  columns at all are ``unknown_field``. Ownership fields (``project_id``, ``document_id``,
  ``source_document_id``, ``code``) are the caller's and may be present but are never required.
* **Never verified by the model.** ``verification_status`` may only be ``Requires review``
  (it is set to that in the cleaned values); ``origin`` may only be ``extracted``.
* **Every item needs a quotation.**
* **Source location only from a verified quotation.** ``page_number`` / ``location_ref`` with
  ``quote_verified`` not ``True`` is rejected: location comes from source provenance, and only
  when the quotation was found.
* **A fact's value must be backed by its quotation** (compared with ``normalize_for_comparison``),
  and a ``date`` fact's ``normalized_value`` must be a strict, plausible ``YYYY-MM-DD`` date whose
  year is visible in the value as written.

Error messages describe the rule and the field only; they never contain the submitted value,
so model or document text cannot leak through a validation report.

Enumerations are matched strictly here. (The extractor deliberately maps an unknown *category*
to ``other`` before building an item; that leniency belongs to the extractor, not to this check.)
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional, Union

from sqlalchemy import Boolean, Enum as SAEnum, Integer, String

from app.models.enums import FactType, RequirementOrigin, VerificationStatus
from app.models.extracted_fact import ExtractedFact
from app.models.requirement import Requirement
from app.models.risk import Risk
from app.models.types import UTCDateTime
from app.services.ingestion.sanitizer import normalize_for_comparison

SCHEMA_VALIDATOR_VERSION = "schema-validator-1.0.0"

MAX_TEXT_CHARS = 100_000  # guard for unbounded Text columns; not a business rule
MAX_JSON_BYTES = 1_000_000  # guard for one JSON payload
MAX_BATCH_ITEMS = 50  # same per-chunk ceiling the extractor applies
_PLAUSIBLE_YEARS = range(1990, 2101)  # mirrors the extractor's date plausibility check
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)

__all__ = [
    "BatchValidation",
    "FieldIssue",
    "PayloadKind",
    "RejectedPayload",
    "SCHEMA_VALIDATOR_VERSION",
    "ValidationResult",
    "parse_json_payload",
    "validate_batch",
    "validate_extracted",
    "validate_json",
]


class PayloadKind(str, Enum):
    REQUIREMENT = "requirement"
    FACT = "fact"
    RISK = "risk"


# ---------------------------------------------------------------------------- specs
@dataclass(frozen=True)
class _Spec:
    model: Any
    permitted: frozenset[str]  # columns an extractor may supply
    caller_fields: frozenset[str]  # ownership columns: allowed, never required
    non_blank: frozenset[str]  # text that must contain characters


_SOURCE_FIELDS = ("page_number", "location_ref", "quotation", "quote_verified", "extractor", "verification_status")

_SPECS: dict[PayloadKind, _Spec] = {
    PayloadKind.REQUIREMENT: _Spec(
        model=Requirement,
        permitted=frozenset(
            ("description", "category", "is_mandatory", "deadline", *_SOURCE_FIELDS,
             "project_id", "source_document_id", "code", "origin")
        ),
        caller_fields=frozenset(("project_id", "source_document_id", "code")),
        non_blank=frozenset(("description", "quotation")),
    ),
    PayloadKind.FACT: _Spec(
        model=ExtractedFact,
        permitted=frozenset(
            ("fact_type", "label", "value", "normalized_value", "unit", *_SOURCE_FIELDS, "document_id")
        ),
        caller_fields=frozenset(("document_id",)),
        non_blank=frozenset(("label", "value", "quotation")),
    ),
    PayloadKind.RISK: _Spec(
        model=Risk,
        permitted=frozenset(
            ("title", "description", "category", *_SOURCE_FIELDS,
             "project_id", "source_document_id", "code", "origin")
        ),
        caller_fields=frozenset(("project_id", "source_document_id", "code")),
        non_blank=frozenset(("title", "quotation")),
    ),
}

# Fields where an extractor may only ever supply one value.
_FIXED: dict[str, Enum] = {
    "verification_status": VerificationStatus.REQUIRES_REVIEW,
    "origin": RequirementOrigin.EXTRACTED,
}


# ------------------------------------------------------------------------- results
@dataclass(frozen=True)
class FieldIssue:
    """One problem. ``field`` is ``""`` for a problem with the payload as a whole. ``message``
    never contains the submitted value."""

    field: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "code": self.code, "message": self.message}


@dataclass(frozen=True)
class ValidationResult:
    """``values`` is the cleaned column values (enums coerced, text stripped, blank optional
    text as ``None``, ``verification_status`` = Requires review) and is ``None`` when invalid."""

    kind: PayloadKind
    values: Optional[dict[str, Any]]
    issues: tuple[FieldIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "ok": self.ok,
            "issues": [i.to_dict() for i in self.issues],
            "version": SCHEMA_VALIDATOR_VERSION,
        }


@dataclass(frozen=True)
class RejectedPayload:
    index: int
    issues: tuple[FieldIssue, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "issues": [i.to_dict() for i in self.issues]}


@dataclass(frozen=True)
class BatchValidation:
    """``accepted`` pairs each valid item's position with its cleaned values; ``issues`` are
    problems with the batch itself (not a list, too many items, unparseable JSON)."""

    kind: PayloadKind
    accepted: tuple[tuple[int, dict[str, Any]], ...]
    rejected: tuple[RejectedPayload, ...]
    issues: tuple[FieldIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues and not self.rejected

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "ok": self.ok,
            "accepted_indexes": [i for i, _ in self.accepted],
            "rejected": [r.to_dict() for r in self.rejected],
            "issues": [i.to_dict() for i in self.issues],
            "version": SCHEMA_VALIDATOR_VERSION,
        }


# ---------------------------------------------------------------------- column rules
def _required_fields(spec: _Spec) -> list[str]:
    """NOT NULL columns without a default (read from the model), plus the quotation the
    extraction contract demands for every item."""
    required = [
        c.name
        for c in spec.model.__table__.columns
        if not c.nullable
        and not c.primary_key
        and c.default is None
        and c.server_default is None
        and c.name not in spec.caller_fields
    ]
    if "quotation" not in required:
        required.append("quotation")
    return required


def _parse_aware_datetime(raw: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _coerce(column: Any, name: str, raw: Any) -> tuple[Any, Optional[FieldIssue]]:
    """Coerce one value to what the column holds, or return the problem. ``None`` is passed
    through; whether it is allowed is decided by the caller."""
    if raw is None:
        return None, None
    ctype = column.type

    if isinstance(ctype, SAEnum):  # before String: Enum subclasses String
        enum_cls = ctype.enum_class
        if isinstance(raw, enum_cls):
            return raw, None
        if isinstance(raw, str):
            try:
                return enum_cls(raw.strip()), None
            except ValueError:
                allowed = ", ".join(m.value for m in enum_cls)
                return None, FieldIssue(name, "invalid_choice", f"must be one of: {allowed}")
        return None, FieldIssue(name, "wrong_type", "must be text matching one of the allowed values")

    if isinstance(ctype, Boolean):
        if isinstance(raw, bool):
            return raw, None
        return None, FieldIssue(name, "wrong_type", "must be true or false")

    if isinstance(ctype, Integer):
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw, None
        return None, FieldIssue(name, "wrong_type", "must be a whole number")

    if isinstance(ctype, UTCDateTime):
        value = _parse_aware_datetime(raw) if isinstance(raw, str) else raw
        if not isinstance(value, datetime):
            return None, FieldIssue(name, "wrong_type", "must be a timezone-aware date and time")
        if value.tzinfo is None:
            return None, FieldIssue(name, "naive_datetime", "must include a timezone; naive date-times are rejected")
        return value, None

    if isinstance(ctype, String):  # String and Text
        if not isinstance(raw, str):
            return None, FieldIssue(name, "wrong_type", "must be text")
        if "\x00" in raw:
            return None, FieldIssue(name, "invalid_characters", "must not contain NUL characters")
        text = raw.strip()
        limit = ctype.length if ctype.length is not None else MAX_TEXT_CHARS
        if len(text) > limit:
            return None, FieldIssue(name, "too_long", f"must be at most {limit} characters")
        return text, None

    return raw, None  # no other column kinds occur in these models


# --------------------------------------------------------------------- cross-field
def _fact_rules(values: Mapping[str, Any], issues: list[FieldIssue]) -> None:
    value, quotation = values.get("value"), values.get("quotation")
    if value and quotation and normalize_for_comparison(value) not in normalize_for_comparison(quotation):
        issues.append(FieldIssue("value", "value_not_in_quotation", "the value as written must appear in the quotation"))

    if values.get("fact_type") is FactType.DATE and values.get("normalized_value") is not None:
        normalized = values["normalized_value"]
        parsed: Optional[date] = None
        if _ISO_DATE.match(normalized):
            try:
                parsed = date.fromisoformat(normalized)
            except ValueError:
                parsed = None
        if parsed is None or parsed.year not in _PLAUSIBLE_YEARS:
            issues.append(FieldIssue("normalized_value", "invalid_date", "must be a plausible calendar date as YYYY-MM-DD"))
        elif not value or str(parsed.year) not in value:
            issues.append(FieldIssue("normalized_value", "year_not_in_value", "the year must be visible in the value as written"))


def _contract_rules(spec: _Spec, values: Mapping[str, Any], issues: list[FieldIssue]) -> None:
    if values.get("page_number") is not None and values["page_number"] < 1:
        issues.append(FieldIssue("page_number", "out_of_range", "must be 1 or greater"))
    located = values.get("page_number") is not None or values.get("location_ref") is not None
    if located and values.get("quote_verified") is not True:
        issues.append(
            FieldIssue("location_ref", "location_without_verified_quote",
                       "page and location come from source provenance and only for a verified quotation")
        )
    if spec.model is ExtractedFact:
        _fact_rules(values, issues)


# ------------------------------------------------------------------------ public API
def _validate_mapping(kind: PayloadKind, data: Any) -> ValidationResult:
    spec = _SPECS[kind]
    if not isinstance(data, Mapping):
        return ValidationResult(kind, None, (FieldIssue("", "not_an_object", "the item must be an object of field values"),))

    issues: list[FieldIssue] = []
    table = spec.model.__table__.columns
    cleaned: dict[str, Any] = {}

    for key in sorted(data, key=str):
        if not isinstance(key, str):
            issues.append(FieldIssue("", "bad_key", "field names must be text"))
            continue
        if key not in table:
            issues.append(FieldIssue(key, "unknown_field", "is not a field of this record"))
            continue
        if key not in spec.permitted:
            issues.append(FieldIssue(key, "not_permitted", "may not be set by extraction; it is assessed or entered by a person"))
            continue
        column = table[key]
        value, issue = _coerce(column, key, data[key])
        if issue is not None:
            issues.append(issue)
        elif isinstance(value, str) and value == "":
            if key in spec.non_blank or not column.nullable:
                issues.append(FieldIssue(key, "blank", "must contain text"))
            else:
                cleaned[key] = None
        elif value is None and not column.nullable:
            issues.append(FieldIssue(key, "null_not_allowed", "must not be null"))
        else:
            cleaned[key] = value

    for key, fixed in _FIXED.items():
        if cleaned.get(key) is not None and cleaned[key] is not fixed:
            issues.append(FieldIssue(key, "not_permitted_value", f"extraction may only set this to '{fixed.value}'"))

    flagged = {i.field for i in issues}
    for key in _required_fields(spec):
        if cleaned.get(key) is None and key not in flagged:
            issues.append(FieldIssue(key, "missing", "is required"))

    if not issues:
        _contract_rules(spec, cleaned, issues)
    if issues:
        return ValidationResult(kind, None, tuple(issues))

    cleaned["verification_status"] = VerificationStatus.REQUIRES_REVIEW
    return ValidationResult(kind, cleaned, ())


def validate_extracted(kind: Union[PayloadKind, str], data: Any) -> ValidationResult:
    """Validate one proposed item. Never raises for bad *data*; an unknown ``kind`` raises
    ``ValueError`` because that is a programming error."""
    return _validate_mapping(PayloadKind(kind), data)


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not valid JSON")


def parse_json_payload(payload: Union[str, bytes]) -> tuple[Any, Optional[FieldIssue]]:
    """Parse model output: JSON, optionally inside a ```json fence. Returns ``(data, None)`` or
    ``(None, issue)``. NaN/Infinity, oversized input and over-deep nesting are rejected."""
    if isinstance(payload, bytes):
        if len(payload) > MAX_JSON_BYTES:
            return None, FieldIssue("", "too_large", "the JSON payload is too large")
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError:
            return None, FieldIssue("", "invalid_json", "the payload is not valid UTF-8 text")
    if not isinstance(payload, str):
        return None, FieldIssue("", "wrong_type", "the payload must be JSON text")
    if len(payload.encode("utf-8")) > MAX_JSON_BYTES:
        return None, FieldIssue("", "too_large", "the JSON payload is too large")
    candidate = payload.strip()
    if not candidate:
        return None, FieldIssue("", "invalid_json", "the payload is empty")
    fenced = _FENCE.match(candidate)
    if fenced:
        candidate = fenced.group(1)
    try:
        return json.loads(candidate, parse_constant=_reject_constant), None
    except (ValueError, RecursionError):
        return None, FieldIssue("", "invalid_json", "the payload is not valid JSON")


def validate_json(kind: Union[PayloadKind, str], payload: Union[str, bytes]) -> ValidationResult:
    """Parse and validate one JSON object."""
    kind = PayloadKind(kind)
    data, issue = parse_json_payload(payload)
    if issue is not None:
        return ValidationResult(kind, None, (issue,))
    return _validate_mapping(kind, data)


def validate_batch(
    kind: Union[PayloadKind, str],
    items: Union[Iterable[Any], str, bytes],
    *,
    key: Optional[str] = None,
    max_items: int = MAX_BATCH_ITEMS,
) -> BatchValidation:
    """Validate a list of proposed items, one result each.

    ``items`` may be a list, or JSON text holding a list or (with ``key``) an object such as
    ``{"requirements": [...]}``. Items beyond ``max_items`` are not validated; the batch
    reports ``too_many_items`` so the omission is visible.
    """
    kind = PayloadKind(kind)
    if isinstance(items, (str, bytes)):
        items, issue = parse_json_payload(items)
        if issue is not None:
            return BatchValidation(kind, (), (), (issue,))
    if isinstance(items, Mapping) and key is not None:
        items = items.get(key)
    if not isinstance(items, (list, tuple)):
        return BatchValidation(kind, (), (), (FieldIssue("", "not_a_list", "expected a list of items"),))

    batch_issues: list[FieldIssue] = []
    if len(items) > max_items:
        batch_issues.append(FieldIssue("", "too_many_items", f"only the first {max_items} items were validated"))
        items = items[:max_items]

    accepted: list[tuple[int, dict[str, Any]]] = []
    rejected: list[RejectedPayload] = []
    for index, item in enumerate(items):
        result = _validate_mapping(kind, item)
        if result.ok and result.values is not None:
            accepted.append((index, result.values))
        else:
            rejected.append(RejectedPayload(index, result.issues))
    return BatchValidation(kind, tuple(accepted), tuple(rejected), tuple(batch_issues))