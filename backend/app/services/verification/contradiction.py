"""Contradiction detection between extracted facts, across documents and versions (FR-14).

Finds *extracted facts* (``ExtractedFact`` rows or mappings) that make incompatible claims
about the same thing, for example a submission deadline of 15 March in the tender and 29 March
in a later addendum. Like ``services/finance`` and ``services/analysis`` this module is made of
*pure functions*: no database access, no clock, no randomness and no language model. Inputs
are duck-typed (SQLAlchemy objects or plain mappings). Nothing is resolved or written: the
report says *what disagrees and where*, and a person decides which source governs.

Scope: ``analysis/gap_detector`` already detects conflicts between *requirements* (different
financial thresholds, identical text with different deadlines or mandatory flags). This module
covers the other half of FR-14, the typed facts extracted from documents.

What counts as a contradiction
------------------------------
Two or more facts are compared only when they are plainly about the same thing **and** their
values are comparable. A contradiction needs at least two *different* comparable values.

1. **Same thing** = same ``fact_type`` and the same label after normalisation (case, spacing and
   punctuation ignored). Labels that merely look similar are *not* grouped: a missed conflict is
   shown to a person elsewhere, a false one wastes their attention. Numeric facts are also
   grouped by ``unit`` (case and spacing ignored); facts with different or missing units are
   never compared, because no unit or currency conversion is invented.
2. **Comparable values** come from ``normalized_value`` only, never from the free-text ``value``:
   ``date`` facts need a strict ``YYYY-MM-DD`` date; ``cost`` and ``quantity`` facts need a plain
   decimal number (thousands separators allowed; ``1500`` equals ``1,500.00``). Other fact types
   (deliverables, conditions, locations, ...) are free text with no sound way to decide
   conflict, so they are not compared.
3. **Incomplete evidence is not a conflict.** A fact with no comparable value, no label, or a
   quotation that failed verification (``quote_verified is False``) is listed under ``skipped``
   with the reason and takes no part in any comparison. ``Rejected`` facts are ignored; ``Outdated``
   and ``Missing`` ones are skipped. ``quote_verified is None`` (not yet checked) still takes
   part, but the finding is flagged ``quotation_unchecked``.
4. **Company data is not compared with tender data.** A company's turnover and a tender's
   minimum turnover are different claims. When ``documents`` is supplied, a fact is compared only
   with facts from documents owned by the same project or the same company; a fact whose document
   is not supplied, or has no owner, is skipped. When ``documents`` is omitted the caller is
   asserting that every fact belongs to one project (or one company) and no scoping is done.
5. **Compatible claims are not flagged**: the same value stated twice (even in different
   documents or on different pages) is agreement.

Provenance and trust
--------------------
Every finding lists each source with its fact id, document (name, type, version when known),
page, location, quotation and verification status exactly as stored; nothing is invented.
Facts that are not ``Verified`` still take part (this is review support) but the finding carries
``basis_unverified``. A finding involving a ``tender_addendum`` is flagged ``includes_addendum``
and notes that an addendum may intentionally change an earlier value; whether it supersedes is a
decision for a person, not made here. ``conflicting_fact_ids`` lists the facts a caller may then
move to ``Conflicting`` with ``records.apply_verification``; this module does not do so itself.
"""
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Optional, Union

from app.models.enums import DocumentType, FactType, VerificationStatus

CONTRADICTION_VERSION = "contradiction-1.0.0"
MAX_QUOTE_CHARS = 300

_VERIFIED = VerificationStatus.VERIFIED.value
_REJECTED = VerificationStatus.REJECTED.value
_OUTDATED = VerificationStatus.OUTDATED.value
_MISSING = VerificationStatus.MISSING.value
_REVIEW = VerificationStatus.REQUIRES_REVIEW.value
_ADDENDUM = DocumentType.TENDER_ADDENDUM.value

_DATE_FACT = FactType.DATE.value
_NUMERIC_FACTS = frozenset({FactType.COST.value, FactType.QUANTITY.value})
_COMPARABLE_FACTS = _NUMERIC_FACTS | {_DATE_FACT}

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NUMBER = re.compile(r"^-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$")

REASONS = {
    "no_label": "The fact has no label, so it cannot be matched with other facts.",
    "no_comparable_value": "No machine-comparable normalized value is recorded, so no conflict can be confirmed or ruled out.",
    "quotation_not_verified": "The quotation was not found in the source, so the claim is unsupported and is not compared.",
    "outdated": "Marked Outdated; not compared.",
    "marked_missing": "Marked Missing; not compared.",
    "document_not_provided": "Its document was not supplied, so the fact cannot be scoped to a project or company.",
    "document_owner_unknown": "Its document has no project or company, so the fact cannot be scoped.",
}


class ConflictKind(str, Enum):
    DATE = "Different dates"
    VALUE = "Different values"


class ConflictScope(str, Enum):
    BETWEEN_DOCUMENTS = "Between documents"
    WITHIN_DOCUMENT = "Within one document"
    UNSPECIFIED = "Source document not recorded"


# --------------------------------------------------------------------------- helpers
def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _value(v: Any) -> Any:
    return getattr(v, "value", v)


def _vstatus(obj: Any) -> str:
    status = _value(_get(obj, "verification_status"))
    return str(status) if status else _REVIEW


def _clip(text: Any, limit: int = 160) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _label_key(label: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(label or "").lower()))


def _unit_key(unit: Any) -> Optional[str]:
    text = " ".join(str(unit or "").lower().split())
    return text or None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "unlabelled"


def _int_or_none(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _parse_value(fact_type: str, normalized: Any) -> Optional[tuple[Any, str]]:
    """``(comparison key, display text)`` for a strict, comparable value; ``None`` otherwise."""
    if not isinstance(normalized, str):
        return None
    text = normalized.strip()
    if fact_type == _DATE_FACT:
        if not _ISO_DATE.match(text):
            return None
        try:
            parsed = date.fromisoformat(text)
        except ValueError:
            return None
        return parsed, parsed.isoformat()
    if not _NUMBER.match(text):
        return None
    try:
        number = Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None
    return number, format(number.normalize(), "f") if number != 0 else "0"


# ------------------------------------------------------------------------- results
@dataclass(frozen=True)
class ClaimSource:
    """Where one conflicting claim came from, as stored."""

    fact_id: Optional[int]
    document_id: Optional[int]
    document_name: Optional[str]
    document_type: Optional[str]
    document_version: Optional[int]
    value: str  # as written in the source
    normalized_value: str  # the comparable form
    unit: Optional[str]
    page_number: Optional[int]
    location_ref: Optional[str]
    quotation: Optional[str]
    quote_verified: Optional[bool]
    verification_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "document_id": self.document_id,
            "document_name": self.document_name,
            "document_type": self.document_type,
            "document_version": self.document_version,
            "value": self.value,
            "normalized_value": self.normalized_value,
            "unit": self.unit,
            "page_number": self.page_number,
            "location_ref": self.location_ref,
            "quotation": self.quotation,
            "quote_verified": self.quote_verified,
            "verification_status": self.verification_status,
        }


@dataclass(frozen=True)
class Contradiction:
    contradiction_id: str
    kind: ConflictKind
    fact_type: str
    label: str
    unit: Optional[str]
    scope: ConflictScope
    distinct_values: tuple[str, ...]
    sources: tuple[ClaimSource, ...]
    flags: tuple[str, ...]
    notes: tuple[str, ...]
    what_would_close_it: str

    @property
    def fact_ids(self) -> tuple[int, ...]:
        return tuple(s.fact_id for s in self.sources if s.fact_id is not None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contradiction_id": self.contradiction_id,
            "kind": self.kind.value,
            "fact_type": self.fact_type,
            "label": self.label,
            "unit": self.unit,
            "scope": self.scope.value,
            "distinct_values": list(self.distinct_values),
            "sources": [s.to_dict() for s in self.sources],
            "fact_ids": list(self.fact_ids),
            "flags": list(self.flags),
            "notes": list(self.notes),
            "what_would_close_it": self.what_would_close_it,
        }


@dataclass(frozen=True)
class SkippedFact:
    """A fact that took no part in any comparison, and why (never silently dropped)."""

    fact_id: Optional[int]
    label: str
    reason: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"fact_id": self.fact_id, "label": self.label, "reason": self.reason, "message": self.message}


@dataclass(frozen=True)
class ContradictionReport:
    contradictions: tuple[Contradiction, ...]
    skipped: tuple[SkippedFact, ...]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "contradictions": [c.to_dict() for c in self.contradictions],
            "skipped": [s.to_dict() for s in self.skipped],
            "summary": self.summary,
        }


def conflicting_fact_ids(report: ContradictionReport) -> tuple[int, ...]:
    """Ids of every fact involved in a contradiction (for a caller that then marks them
    ``Conflicting``). Nothing is changed here."""
    return tuple(sorted({fid for c in report.contradictions for fid in c.fact_ids}))


# ------------------------------------------------------------------------ analysis
@dataclass(frozen=True)
class _Claim:
    fact: Any
    fact_id: Optional[int]
    fact_type: str
    label: str
    unit: Optional[str]
    key: Any
    shown: str
    document: Any


def _index_documents(documents: Union[Mapping[Any, Any], Iterable[Any], None]) -> Optional[dict[Any, Any]]:
    if documents is None:
        return None
    if isinstance(documents, Mapping):
        return dict(documents)
    return {_get(d, "id"): d for d in documents if _get(d, "id") is not None}


def _owner(document: Any) -> Optional[tuple[str, Any]]:
    if _get(document, "project_id") is not None:
        return "project", _get(document, "project_id")
    if _get(document, "company_id") is not None:
        return "company", _get(document, "company_id")
    return None


def _source(claim: _Claim) -> ClaimSource:
    fact, doc = claim.fact, claim.document
    quotation = _clip(_get(fact, "quotation"), MAX_QUOTE_CHARS) or None
    quote_verified = _get(fact, "quote_verified")
    version = _get(doc, "version")
    return ClaimSource(
        fact_id=_get(fact, "id"),
        document_id=_get(fact, "document_id"),
        document_name=_get(doc, "original_filename"),
        document_type=_value(_get(doc, "document_type")),
        document_version=version if isinstance(version, int) and not isinstance(version, bool) else None,
        value=_clip(_get(fact, "value"), MAX_QUOTE_CHARS),
        normalized_value=claim.shown,
        unit=claim.unit,
        page_number=_get(fact, "page_number"),
        location_ref=_get(fact, "location_ref"),
        quotation=quotation,
        quote_verified=quote_verified if isinstance(quote_verified, bool) else None,
        verification_status=_vstatus(fact),
    )


def _finding(owner: Optional[tuple[str, Any]], fact_type: str, unit: Optional[str], label_key: str, claims: list[_Claim]) -> Contradiction:
    claims = sorted(claims, key=lambda c: (_int_or_none(_get(c.fact, "document_id")) or 0, c.fact_id or 0, c.shown))
    sources = tuple(_source(c) for c in claims)
    distinct = tuple(sorted({s.normalized_value for s in sources}))
    doc_ids = {s.document_id for s in sources}
    if None in doc_ids:
        scope = ConflictScope.UNSPECIFIED
    elif len(doc_ids) > 1:
        scope = ConflictScope.BETWEEN_DOCUMENTS
    else:
        scope = ConflictScope.WITHIN_DOCUMENT

    flags: list[str] = []
    notes: list[str] = []
    if any(s.verification_status != _VERIFIED for s in sources):
        flags.append("basis_unverified")
        notes.append("At least one claim is not Verified; confirm the sources before relying on either value.")
    if any(s.quote_verified is None for s in sources):
        flags.append("quotation_unchecked")
        notes.append("At least one quotation has not been checked against its source text.")
    if any(s.document_type == _ADDENDUM for s in sources):
        flags.append("includes_addendum")
        notes.append("An addendum may intentionally change an earlier value; which one governs is a decision for a person.")
    if len({s.document_version for s in sources if s.document_version is not None}) > 1:
        flags.append("multiple_document_versions")
    if scope is ConflictScope.WITHIN_DOCUMENT:
        notes.append("Both claims are in one document; they may refer to different items (for example separate lots) or be an extraction error.")
    if scope is ConflictScope.UNSPECIFIED:
        notes.append("At least one claim has no recorded source document.")

    label = str(_get(claims[0].fact, "label") or "").strip()
    owner_tag = f"-{owner[0]}{owner[1]}" if owner else ""
    unit_tag = f"-{_slug(unit)}" if unit else ""
    return Contradiction(
        contradiction_id=f"CONTRA-{fact_type}-{_slug(label_key)}{unit_tag}{owner_tag}",
        kind=ConflictKind.DATE if fact_type == _DATE_FACT else ConflictKind.VALUE,
        fact_type=fact_type,
        label=label,
        unit=unit,
        scope=scope,
        distinct_values=distinct,
        sources=sources,
        flags=tuple(flags),
        notes=tuple(notes),
        what_would_close_it="Ask the client which document or version is authoritative and record the answer; then confirm or reject the facts that do not apply.",
    )


def detect_contradictions(
    facts: Iterable[Any],
    documents: Union[Mapping[Any, Any], Iterable[Any], None] = None,
) -> ContradictionReport:
    """Find extracted facts that make incompatible claims about the same thing.

    ``facts``: ``ExtractedFact`` objects or mappings. ``documents``: optional ``Document``
    objects (or mappings), as an iterable or an ``{id: document}`` mapping, used to name sources
    and to keep project and company data apart (see the module docstring).
    """
    index = _index_documents(documents)
    skipped: list[SkippedFact] = []
    ignored_rejected = 0
    unsupported_type = 0
    seen_ids: set[Any] = set()
    groups: dict[tuple, list[_Claim]] = defaultdict(list)
    units_by_label: dict[tuple, set[Optional[str]]] = defaultdict(set)
    considered = 0

    def skip(fact: Any, reason: str) -> None:
        skipped.append(SkippedFact(_get(fact, "id"), _clip(_get(fact, "label"), 80), reason, REASONS[reason]))

    for fact in facts:
        fact_id = _get(fact, "id")
        if fact_id is not None:
            if fact_id in seen_ids:
                continue
            seen_ids.add(fact_id)
        status = _vstatus(fact)
        if status == _REJECTED:
            ignored_rejected += 1
            continue
        fact_type = str(_value(_get(fact, "fact_type")) or FactType.OTHER.value)
        if fact_type not in _COMPARABLE_FACTS:
            unsupported_type += 1
            continue
        considered += 1
        if status == _OUTDATED:
            skip(fact, "outdated")
            continue
        if status == _MISSING:
            skip(fact, "marked_missing")
            continue
        label_key = _label_key(_get(fact, "label"))
        if not label_key:
            skip(fact, "no_label")
            continue
        if _get(fact, "quote_verified") is False:
            skip(fact, "quotation_not_verified")
            continue
        parsed = _parse_value(fact_type, _get(fact, "normalized_value"))
        if parsed is None:
            skip(fact, "no_comparable_value")
            continue

        document = None
        owner: Optional[tuple[str, Any]] = None
        if index is not None:
            document = index.get(_get(fact, "document_id"))
            if document is None:
                skip(fact, "document_not_provided")
                continue
            owner = _owner(document)
            if owner is None:
                skip(fact, "document_owner_unknown")
                continue

        unit = _unit_key(_get(fact, "unit")) if fact_type in _NUMERIC_FACTS else None
        claim = _Claim(fact, fact_id, fact_type, label_key, unit, parsed[0], parsed[1], document)
        groups[(owner, fact_type, label_key, unit)].append(claim)
        units_by_label[(owner, fact_type, label_key)].add(unit)

    contradictions = []
    comparable_groups = 0
    for (owner, fact_type, label_key, unit) in sorted(groups, key=lambda k: (str(k[0]), k[1], k[2], k[3] or "")):
        claims = groups[(owner, fact_type, label_key, unit)]
        if len(claims) < 2:
            continue
        comparable_groups += 1
        if len({c.key for c in claims}) >= 2:
            contradictions.append(_finding(owner, fact_type, unit, label_key, claims))

    by_reason: dict[str, int] = defaultdict(int)
    for s in skipped:
        by_reason[s.reason] += 1
    summary = {
        "facts_considered": considered,
        "facts_compared": sum(len(c) for c in groups.values()),
        "comparable_groups": comparable_groups,
        "contradictions": len(contradictions),
        "skipped": len(skipped),
        "skipped_by_reason": dict(sorted(by_reason.items())),
        "ignored_rejected": ignored_rejected,
        "not_compared_unsupported_type": unsupported_type,
        "labels_with_different_units": sum(1 for units in units_by_label.values() if len(units) > 1),
        "basis": (
            "Only date, cost and quantity facts with the same label (and unit) and a strict normalized value "
            "are compared. Missing, unverified or unscoped evidence is skipped, never treated as a conflict. "
            "Which source governs is left to a person."
        ),
        "version": CONTRADICTION_VERSION,
    }
    return ContradictionReport(tuple(contradictions), tuple(skipped), summary)