"""Gap detection: what the company lacks, what is unknown, what conflicts (FR-17).

Turns requirement states (and optionally the company profile) into a list of *findings* using
the PRD finding types: Missing information, Potential issue, Contradiction, Unverified
assumption, External verification required. Like ``services/finance`` this module is made of
*pure functions*: no database access, no clock (``as_of`` is an argument), no randomness and no
language model. The same inputs always give the same findings in the same order.

Inputs
------
``detect_gaps(requirements, match_results=None, *, company=None, as_of=None)``

* ``requirements``: ``Requirement`` objects or mappings. ``Rejected`` ones are skipped.
* ``match_results``: optional ``MatchResult`` list from ``requirement_matcher``. When omitted,
  each requirement's *stored* ``match_status`` / ``evidence_summary`` / ``missing_evidence`` are
  analysed, which is what the UI wants after a person has edited statuses by hand.
* ``company``: optional; adds company-profile gaps and profile conflicts.

How a requirement becomes a finding
-----------------------------------
=========================================  ====================================================
Match state                                Finding
=========================================  ====================================================
Not met / Partially met                    Potential issue
Unknown, evidence not yet confirmed        Unverified assumption (what it would be if confirmed)
Unknown, no or insufficient evidence       Missing information (what evidence would close it)
Conflicting company records                Contradiction (and no other finding for that row)
Met / Not applicable                       none (Met with unconfirmed evidence is Unknown above)
=========================================  ====================================================

Plus: a legal/contractual requirement always gets an *External verification required* finding
(ProjectIQ never assesses legal compliance), and cross-requirement contradictions are raised
for (a) different amounts for the same financial metric and (b) identical requirement text with
different deadlines or a different mandatory flag, with every source listed and the question
"which is authoritative?" left to a person. Nothing is resolved automatically.

Severity (mandatory flag from the source; ``None`` means the source does not say)
---------------------------------------------------------------------------------
==============  =========  ==========  ==========
status          mandatory  unspecified optional
==============  =========  ==========  ==========
Not met         critical   high        medium
Partially met   high       medium      low
Unknown         high       medium      low
==============  =========  ==========  ==========

An unverified assumption takes the severity of its provisional status, one level lower
(a provisional Met is low). ``blocking`` is true for a *mandatory* requirement that is not yet
Met or Not applicable, and for a contradiction touching a mandatory requirement: it means "a
person must resolve this before the bid decision", not "the company cannot bid". An unspecified
mandatory flag is never assumed either way; the finding says so.

No overall score or verdict is produced.
"""
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from app.models.enums import MatchStatus, RequirementCategory, VerificationStatus
from app.services.analysis.requirement_matcher import MatchResult, extract_financial_requirement

GAP_DETECTOR_VERSION = "gap-detector-1.0.0"

_REJECTED = VerificationStatus.REJECTED.value
_VERIFIED = VerificationStatus.VERIFIED.value
_CONFLICTING = VerificationStatus.CONFLICTING.value
_MISSING = VerificationStatus.MISSING.value
_REVIEW = VerificationStatus.REQUIRES_REVIEW.value
_UNCONFIRMED = frozenset(
    {
        VerificationStatus.REQUIRES_REVIEW.value,
        VerificationStatus.ESTIMATED.value,
        VerificationStatus.ASSUMPTION.value,
        VerificationStatus.OUTDATED.value,
    }
)

_MET, _PARTIAL, _NOT_MET = MatchStatus.MET, MatchStatus.PARTIALLY_MET, MatchStatus.NOT_MET
_UNKNOWN, _NA = MatchStatus.UNKNOWN, MatchStatus.NOT_APPLICABLE

MAX_QUOTE_CHARS = 300


class GapType(str, Enum):
    MISSING_INFORMATION = "Missing information"
    POTENTIAL_ISSUE = "Potential issue"
    CONTRADICTION = "Contradiction"
    UNVERIFIED_ASSUMPTION = "Unverified assumption"
    EXTERNAL_VERIFICATION = "External verification required"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class GapScope(str, Enum):
    REQUIREMENT = "requirement"
    CROSS_REQUIREMENT = "cross_requirement"
    COMPANY_PROFILE = "company_profile"


_SEVERITY_ORDER = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
_TYPE_ORDER = {t: i for i, t in enumerate(GapType)}
_SCOPE_ORDER = {GapScope.REQUIREMENT: 0, GapScope.CROSS_REQUIREMENT: 1, GapScope.COMPANY_PROFILE: 2}
_TYPE_SLUG = {
    GapType.MISSING_INFORMATION: "missing",
    GapType.POTENTIAL_ISSUE: "issue",
    GapType.CONTRADICTION: "conflict",
    GapType.UNVERIFIED_ASSUMPTION: "unverified",
    GapType.EXTERNAL_VERIFICATION: "external",
}
_SEVERITY_TABLE = {
    (_NOT_MET, True): Severity.CRITICAL, (_NOT_MET, None): Severity.HIGH, (_NOT_MET, False): Severity.MEDIUM,
    (_PARTIAL, True): Severity.HIGH, (_PARTIAL, None): Severity.MEDIUM, (_PARTIAL, False): Severity.LOW,
    (_UNKNOWN, True): Severity.HIGH, (_UNKNOWN, None): Severity.MEDIUM, (_UNKNOWN, False): Severity.LOW,
}
_DOWNGRADE = {
    Severity.CRITICAL: Severity.HIGH, Severity.HIGH: Severity.MEDIUM,
    Severity.MEDIUM: Severity.LOW, Severity.LOW: Severity.LOW,
}
_DEFAULT_CLOSE = {
    _NOT_MET: "Evidence that the company does meet this requirement, a partner or subcontractor that does, or a documented decision to accept the gap.",
    _PARTIAL: "Evidence for the part of the requirement that is not yet shown, or a documented decision to accept the shortfall.",
    _UNKNOWN: "Company evidence for this requirement, confirmed by a person.",
}


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


def _code_key(code: str) -> tuple:
    """Natural-sort key ("REQ-2" < "REQ-10"). Parts are tagged so digits and text never compare."""
    return tuple(
        (0, int(p), "") if p.isdigit() else (1, 0, p.lower())
        for p in re.split(r"(\d+)", str(code or ""))
        if p
    )


def _to_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def _status_of(value: Any) -> MatchStatus:
    try:
        return MatchStatus(_value(value))
    except ValueError:
        return _UNKNOWN


def _category_of(req: Any) -> RequirementCategory:
    try:
        return RequirementCategory(_value(_get(req, "category")))
    except ValueError:
        return RequirementCategory.OTHER


def _mandatory_text(flag: Optional[bool]) -> str:
    if flag is True:
        return "mandatory"
    if flag is False:
        return "optional"
    return "not stated as mandatory or optional in the source"


def _field_status(company: Any, name: str) -> str:
    entry = (_get(company, "field_verification") or {}).get(name)
    if isinstance(entry, Mapping) and entry.get("status"):
        return str(entry["status"])
    return _MISSING if _get(company, name) in (None, "", []) else _REVIEW


# ---------------------------------------------------------------------------- result
@dataclass(frozen=True)
class Gap:
    """One finding. ``sources`` are the requirement source references (document, page or
    location, quotation); company-profile findings have none because they describe what is
    absent from the profile."""

    gap_id: str
    gap_type: GapType
    severity: Severity
    scope: GapScope
    title: str
    detail: str
    blocking: bool
    requirement_code: Optional[str] = None
    requirement_id: Optional[int] = None
    requirement_text: Optional[str] = None
    match_status: Optional[str] = None
    provisional_status: Optional[str] = None
    is_mandatory: Optional[bool] = None
    evidence_summary: Optional[str] = None
    what_would_close_it: Optional[str] = None
    related_codes: tuple[str, ...] = ()
    sources: tuple[Mapping[str, Any], ...] = ()
    requirement_reviewed: Optional[bool] = None

    @property
    def has_source(self) -> bool:
        return bool(self.sources) and all(_source_is_linked(s) for s in self.sources)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "gap_type": self.gap_type.value,
            "severity": self.severity.value,
            "scope": self.scope.value,
            "title": self.title,
            "detail": self.detail,
            "blocking": self.blocking,
            "requirement_code": self.requirement_code,
            "requirement_id": self.requirement_id,
            "requirement_text": self.requirement_text,
            "match_status": self.match_status,
            "provisional_status": self.provisional_status,
            "is_mandatory": self.is_mandatory,
            "evidence_summary": self.evidence_summary,
            "what_would_close_it": self.what_would_close_it,
            "related_codes": list(self.related_codes),
            "sources": [dict(s) for s in self.sources],
            "has_source": self.has_source,
            "requirement_reviewed": self.requirement_reviewed,
        }


@dataclass(frozen=True)
class GapReport:
    gaps: tuple[Gap, ...]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"gaps": [g.to_dict() for g in self.gaps], "summary": self.summary}


def _source(req: Any) -> dict[str, Any]:
    return {
        "requirement_code": str(_get(req, "code") or ""),
        "document_id": _get(req, "source_document_id"),
        "page_number": _get(req, "page_number"),
        "location_ref": _get(req, "location_ref"),
        "quotation": _clip(_get(req, "quotation"), MAX_QUOTE_CHARS) or None,
        "quote_verified": _get(req, "quote_verified"),
    }


def _source_is_linked(src: Mapping[str, Any]) -> bool:
    return src.get("document_id") is not None and bool(
        src.get("quotation") or src.get("location_ref") or src.get("page_number")
    )


@dataclass(frozen=True)
class _Assessment:
    status: MatchStatus
    evidence_summary: Optional[str]
    missing_evidence: Optional[str]
    provisional: Optional[MatchStatus] = None
    needs_verification: bool = False
    conflict: bool = False


def _assessment(req: Any, result: Optional[MatchResult]) -> _Assessment:
    if result is not None:
        return _Assessment(
            result.status, result.evidence_summary, result.missing_evidence,
            result.provisional_status, result.needs_verification, result.conflict,
        )
    return _Assessment(
        _status_of(_get(req, "match_status")), _get(req, "evidence_summary"), _get(req, "missing_evidence")
    )


# --------------------------------------------------------------- requirement-level gaps
def _requirement_gaps(req: Any, a: _Assessment) -> list[Gap]:
    code = str(_get(req, "code") or "")
    mandatory = _get(req, "is_mandatory")
    mandatory = mandatory if isinstance(mandatory, bool) else None
    category = _category_of(req)
    reviewed = _vstatus(req) == _VERIFIED
    text = _clip(_get(req, "description"))
    sources = (_source(req),)
    notes = []
    if mandatory is None:
        notes.append("The source does not say whether this is mandatory, so it is not assumed either way.")
    if not reviewed and _vstatus(req) in _UNCONFIRMED | {_CONFLICTING}:
        notes.append("The requirement text itself has not been reviewed by a person.")
    if _get(req, "quote_verified") is False:
        notes.append("The supporting quotation could not be verified in the source document.")
    suffix = (" " + " ".join(notes)) if notes else ""
    base = dict(
        scope=GapScope.REQUIREMENT, requirement_code=code, requirement_id=_get(req, "id"),
        requirement_text=text, match_status=a.status.value,
        provisional_status=a.provisional.value if a.provisional else None, is_mandatory=mandatory,
        evidence_summary=a.evidence_summary, sources=sources, requirement_reviewed=reviewed,
    )

    def gid(kind: GapType) -> str:
        return f"GAP-{code}-{_TYPE_SLUG[kind]}"

    gaps: list[Gap] = []
    open_status = a.status not in (_MET, _NA)
    blocking = mandatory is True and open_status

    if a.status is not _NA:
        if a.conflict:
            sev = Severity.HIGH if mandatory is not False else Severity.MEDIUM
            gaps.append(Gap(
                gap_id=gid(GapType.CONTRADICTION), gap_type=GapType.CONTRADICTION, severity=sev,
                title=f"{code}: conflicting company records",
                detail=f"Company records used to assess this {_mandatory_text(mandatory)} requirement conflict, so no status can be given."
                       + (f" {a.evidence_summary}." if a.evidence_summary else "") + suffix,
                blocking=blocking,
                what_would_close_it=a.missing_evidence or "A person must resolve the conflicting records.",
                **base,
            ))
        elif a.status in (_NOT_MET, _PARTIAL):
            label = "not met" if a.status is _NOT_MET else "partially met"
            gaps.append(Gap(
                gap_id=gid(GapType.POTENTIAL_ISSUE), gap_type=GapType.POTENTIAL_ISSUE,
                severity=_SEVERITY_TABLE[(a.status, mandatory)],
                title=f"{code}: requirement {label}",
                detail=f"This {_mandatory_text(mandatory)} requirement is {label}."
                       + (f" Evidence: {a.evidence_summary}." if a.evidence_summary else "") + suffix,
                blocking=blocking,
                what_would_close_it=a.missing_evidence or _DEFAULT_CLOSE[a.status],
                **base,
            ))
        elif a.status is _UNKNOWN and a.needs_verification:
            if a.provisional is _MET:
                sev = Severity.LOW
            else:
                sev = _DOWNGRADE[_SEVERITY_TABLE[(a.provisional or _UNKNOWN, mandatory)]]
            prov = f" It would be {a.provisional.value} if the evidence is confirmed." if a.provisional else ""
            gaps.append(Gap(
                gap_id=gid(GapType.UNVERIFIED_ASSUMPTION), gap_type=GapType.UNVERIFIED_ASSUMPTION, severity=sev,
                title=f"{code}: evidence needs confirmation",
                detail=f"The evidence for this {_mandatory_text(mandatory)} requirement has not been confirmed by a person, so its status stays Unknown.{prov}"
                       + (f" Evidence: {a.evidence_summary}." if a.evidence_summary else "") + suffix,
                blocking=blocking,
                what_would_close_it=a.missing_evidence or "Confirm or correct the company records used.",
                **base,
            ))
        elif a.status is _UNKNOWN:
            gaps.append(Gap(
                gap_id=gid(GapType.MISSING_INFORMATION), gap_type=GapType.MISSING_INFORMATION,
                severity=_SEVERITY_TABLE[(_UNKNOWN, mandatory)],
                title=f"{code}: cannot be assessed",
                detail=f"There is not enough evidence to assess this {_mandatory_text(mandatory)} requirement; it stays Unknown, not Not met."
                       + (f" Evidence considered: {a.evidence_summary}." if a.evidence_summary else "") + suffix,
                blocking=blocking,
                what_would_close_it=a.missing_evidence or _DEFAULT_CLOSE[_UNKNOWN],
                **base,
            ))

        if category is RequirementCategory.LEGAL_CONTRACTUAL:
            sev = Severity.LOW if a.status is _MET else (Severity.HIGH if mandatory is True else Severity.MEDIUM)
            gaps.append(Gap(
                gap_id=gid(GapType.EXTERNAL_VERIFICATION), gap_type=GapType.EXTERNAL_VERIFICATION, severity=sev,
                title=f"{code}: legal or contractual review required",
                detail="ProjectIQ does not assess legal compliance or contract terms. A qualified person must review this clause."
                       + suffix,
                blocking=False,
                what_would_close_it="Review by a qualified legal professional, with the outcome recorded on the requirement.",
                **base,
            ))
    return gaps


# ------------------------------------------------------ cross-requirement contradictions
def _norm_text(text: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower()))


def _contradictions(requirements: list[Any]) -> list[Gap]:
    gaps: list[Gap] = []
    ordered = sorted(requirements, key=lambda r: _code_key(str(_get(r, "code") or "")))

    # (a) the same financial metric with different amounts (same currency)
    by_metric: dict[tuple[str, str], list[tuple[Any, Any]]] = defaultdict(list)
    for req in ordered:
        threshold = extract_financial_requirement(_get(req, "description"))
        if threshold is not None:
            by_metric[(threshold.metric, threshold.amount.currency)].append((req, threshold))
    for (metric, currency), rows in sorted(by_metric.items()):
        if len({t.amount.value for _, t in rows}) < 2:
            continue
        codes = tuple(str(_get(r, "code") or "") for r, _ in rows)
        listing = "; ".join(f"{_get(r, 'code')}: {currency} {t.amount.value:,.2f}" for r, t in rows)
        label = metric.replace("_", " ")
        mandatory_any = any(_get(r, "is_mandatory") is True for r, _ in rows)
        gaps.append(Gap(
            gap_id=f"GAP-XREQ-{metric}-{currency}", gap_type=GapType.CONTRADICTION,
            severity=Severity.HIGH if mandatory_any else Severity.MEDIUM, scope=GapScope.CROSS_REQUIREMENT,
            title=f"Different {label} thresholds ({', '.join(codes)})",
            detail=f"Requirements state different {label} amounts: {listing}. Which one is authoritative?",
            blocking=mandatory_any, related_codes=codes, sources=tuple(_source(r) for r, _ in rows),
            what_would_close_it="Ask the client which requirement is authoritative (for example an addendum) and record the answer.",
        ))

    # (b) identical requirement text with different deadlines or mandatory flags
    by_text: dict[str, list[Any]] = defaultdict(list)
    for req in ordered:
        key = _norm_text(_get(req, "description"))
        if len(key.split()) >= 3:
            by_text[key].append(req)
    for key in sorted(by_text):
        rows = by_text[key]
        if len(rows) < 2:
            continue
        deadlines = {_get(r, "deadline") for r in rows if _get(r, "deadline") is not None}
        flags = {_get(r, "is_mandatory") for r in rows if isinstance(_get(r, "is_mandatory"), bool)}
        problems = []
        if len(deadlines) > 1:
            problems.append("deadlines: " + "; ".join(
                f"{_get(r, 'code')}: {_fmt_deadline(_get(r, 'deadline'))}" for r in rows if _get(r, "deadline") is not None))
        if len(flags) > 1:
            problems.append("mandatory flag: " + "; ".join(
                f"{_get(r, 'code')}: {_mandatory_text(_get(r, 'is_mandatory'))}" for r in rows
                if isinstance(_get(r, "is_mandatory"), bool)))
        if not problems:
            continue
        codes = tuple(str(_get(r, "code") or "") for r in rows)
        mandatory_any = any(_get(r, "is_mandatory") is True for r in rows)
        gaps.append(Gap(
            gap_id=f"GAP-XREQ-{'-'.join(codes)}", gap_type=GapType.CONTRADICTION,
            severity=Severity.HIGH if mandatory_any else Severity.MEDIUM, scope=GapScope.CROSS_REQUIREMENT,
            title=f"Requirements disagree ({', '.join(codes)})",
            detail=f"The same requirement is recorded more than once with different {' and '.join(problems)}. Which source is authoritative?",
            blocking=mandatory_any, requirement_text=_clip(_get(rows[0], "description")), related_codes=codes,
            sources=tuple(_source(r) for r in rows),
            what_would_close_it="Ask the client which document is authoritative (for example an addendum) and record the answer.",
        ))
    return gaps


def _fmt_deadline(value: Any) -> str:
    return value.isoformat() if isinstance(value, (date, datetime)) else str(value)


# ------------------------------------------------------------------ company profile gaps
def _profile_gap(slug: str, kind: GapType, severity: Severity, title: str, detail: str, close: str) -> Gap:
    return Gap(
        gap_id=f"GAP-PROFILE-{slug}", gap_type=kind, severity=severity, scope=GapScope.COMPANY_PROFILE,
        title=title, detail=detail, blocking=False, what_would_close_it=close,
    )


def _label(row: Any, *names: str) -> str:
    for n in names:
        if _get(row, n):
            return _clip(_get(row, n), 60)
    return f"record {_get(row, 'id')}"


def detect_profile_gaps(company: Any, *, as_of: Optional[date] = None) -> list[Gap]:
    """What the company profile lacks or holds in conflict. Nothing is inferred: an empty
    section is reported as missing information, never as a missing capability."""
    if company is None:
        return []
    gaps: list[Gap] = []
    sections = {
        "certifications": ("Certifications", "name"),
        "equipment": ("Equipment", "name"),
        "workforce_roles": ("Workforce roles", "role"),
        "past_projects": ("Past projects", "title"),
    }
    rows = {key: [r for r in (_get(company, key) or []) if _vstatus(r) != _REJECTED] for key in sections}

    scalars = {
        "annual_revenue": "annual revenue (turnover)",
        "working_capital": "working capital",
        "bank_guarantee_limit": "bank guarantee limit",
    }
    for field_name, label in scalars.items():
        if _get(company, field_name) is None or _field_status(company, field_name) in (_REJECTED, _MISSING):
            gaps.append(_profile_gap(
                f"{field_name}-missing", GapType.MISSING_INFORMATION, Severity.MEDIUM,
                f"Company {label} is not recorded",
                f"Financial requirements that refer to {label} cannot be assessed until it is provided.",
                f"Enter the company's {label} and mark it Verified once confirmed.",
            ))
    for key, (title, _name) in sections.items():
        if not rows[key]:
            gaps.append(_profile_gap(
                f"{key}-empty", GapType.MISSING_INFORMATION, Severity.MEDIUM,
                f"No {title.lower()} recorded",
                f"The profile has no {title.lower()}. Requirements that depend on them stay Unknown, which is not the same as Not met.",
                f"Add the company's {title.lower()} or upload the document that lists them.",
            ))

    no_expiry = [r for r in rows["certifications"] if _get(r, "expiry_date") is None]
    if no_expiry:
        gaps.append(_profile_gap(
            "certifications-no-expiry", GapType.MISSING_INFORMATION, Severity.LOW,
            "Certifications without an expiry date",
            "Validity cannot be confirmed for: " + ", ".join(_label(r, "name") for r in no_expiry) + ".",
            "Add the expiry date of each certificate.",
        ))
    if as_of is not None:
        expired = [
            r for r in rows["certifications"]
            if _to_date(_get(r, "expiry_date")) is not None and _to_date(_get(r, "expiry_date")) < as_of
        ]
        if expired:
            gaps.append(_profile_gap(
                "certifications-expired", GapType.POTENTIAL_ISSUE, Severity.MEDIUM,
                "Certifications have expired",
                "Recorded as expired: " + ", ".join(
                    f"{_label(r, 'name')} ({_to_date(_get(r, 'expiry_date')).isoformat()})" for r in expired) + ".",
                "Add the renewed certificates, or confirm they are no longer needed.",
            ))
    no_availability = [r for r in rows["workforce_roles"] if _get(r, "available_headcount") is None]
    if no_availability:
        gaps.append(_profile_gap(
            "workforce-availability-unknown", GapType.MISSING_INFORMATION, Severity.MEDIUM,
            "Availability not recorded for some roles",
            "Employed does not mean available. Availability is unknown for: "
            + ", ".join(_label(r, "role") for r in no_availability) + ".",
            "Record how many people in each role are actually available for new work.",
        ))
    incomplete_equipment = [
        r for r in rows["equipment"]
        if not _get(r, "capacity") or _value(_get(r, "ownership")) in (None, "unknown")
    ]
    if incomplete_equipment:
        gaps.append(_profile_gap(
            "equipment-incomplete", GapType.MISSING_INFORMATION, Severity.LOW,
            "Equipment records missing capacity or ownership",
            "Capacity or ownership is not recorded for: "
            + ", ".join(_label(r, "name") for r in incomplete_equipment) + ".",
            "Add the capacity and whether each item is owned or leased.",
        ))

    unconfirmed: dict[str, int] = {}
    conflicting: list[str] = []
    for field_name in scalars:
        status = _field_status(company, field_name)
        if _get(company, field_name) is None:
            continue
        if status in _UNCONFIRMED:
            unconfirmed["Company finances"] = unconfirmed.get("Company finances", 0) + 1
        elif status == _CONFLICTING:
            conflicting.append(scalars[field_name])
    for key, (title, name_field) in sections.items():
        for r in rows[key]:
            status = _vstatus(r)
            if status in _UNCONFIRMED:
                unconfirmed[title] = unconfirmed.get(title, 0) + 1
            elif status == _CONFLICTING:
                conflicting.append(f"{title.lower()}: {_label(r, name_field)}")
    if conflicting:
        gaps.append(_profile_gap(
            "conflicts", GapType.CONTRADICTION, Severity.HIGH,
            "Company profile contains conflicting values",
            "Conflicting: " + "; ".join(conflicting) + ".",
            "Decide which value is correct and mark it Verified (reject the other).",
        ))
    if unconfirmed:
        detail = ", ".join(f"{section}: {count}" for section, count in sorted(unconfirmed.items()))
        gaps.append(_profile_gap(
            "unverified", GapType.UNVERIFIED_ASSUMPTION, Severity.MEDIUM,
            "Company facts not yet confirmed",
            f"Facts still Requires review, Estimated, Assumption or Outdated ({detail}). They cannot make a requirement Met.",
            "Confirm or correct each fact in the company profile.",
        ))
    return gaps


# ------------------------------------------------------------------------- public API
def _sort_key(g: Gap) -> tuple:
    return (
        _SEVERITY_ORDER[g.severity], 0 if g.blocking else 1, _SCOPE_ORDER[g.scope],
        _code_key(g.requirement_code or (g.related_codes[0] if g.related_codes else "")),
        _TYPE_ORDER[g.gap_type], g.gap_id,
    )


def detect_gaps(
    requirements: Iterable[Any],
    match_results: Optional[Iterable[MatchResult]] = None,
    *,
    company: Any = None,
    as_of: Optional[date] = None,
) -> GapReport:
    """Findings for a project's requirements (and, if given, the company profile)."""
    reqs = [r for r in requirements if _vstatus(r) != _REJECTED]
    by_id: dict[Any, MatchResult] = {}
    by_code: dict[str, MatchResult] = {}
    for result in match_results or ():
        if result.requirement_id is not None:
            by_id[result.requirement_id] = result
        by_code[result.requirement_code] = result

    gaps: list[Gap] = []
    statuses = {s.value: 0 for s in MatchStatus}
    mandatory_open = unspecified = unreviewed = 0
    for req in reqs:
        result = by_id.get(_get(req, "id")) or by_code.get(str(_get(req, "code") or ""))
        a = _assessment(req, result)
        statuses[a.status.value] += 1
        flag = _get(req, "is_mandatory")
        if a.status is not _NA:
            if flag is True and a.status is not _MET:
                mandatory_open += 1
            if not isinstance(flag, bool):
                unspecified += 1
        if _vstatus(req) in _UNCONFIRMED | {_CONFLICTING}:
            unreviewed += 1
        gaps.extend(_requirement_gaps(req, a))
    gaps.extend(_contradictions(reqs))
    gaps.extend(detect_profile_gaps(company, as_of=as_of))
    gaps.sort(key=_sort_key)

    req_gaps = [g for g in gaps if g.scope is not GapScope.COMPANY_PROFILE]
    summary = {
        "requirements_total": len(reqs),
        "requirements_by_status": statuses,
        "requirements_unknown": statuses[_UNKNOWN.value],
        "mandatory_not_yet_met": mandatory_open,
        "mandatory_unspecified": unspecified,
        "requirements_unreviewed": unreviewed,
        "gaps_total": len(gaps),
        "by_type": {t.value: sum(1 for g in gaps if g.gap_type is t) for t in GapType},
        "by_severity": {s.value: sum(1 for g in gaps if g.severity is s) for s in Severity},
        "blocking": sum(1 for g in gaps if g.blocking),
        "requirement_gaps_with_source": sum(1 for g in req_gaps if g.has_source),
        "requirement_gaps_without_source": sum(1 for g in req_gaps if not g.has_source),
        "basis": (
            "Findings come from requirement match states and the company profile. Unknown means not "
            "assessed, never failed. Blocking means a person must resolve it before the bid decision. "
            "No overall score or verdict is produced."
        ),
        "version": GAP_DETECTOR_VERSION,
    }
    return GapReport(tuple(gaps), summary)