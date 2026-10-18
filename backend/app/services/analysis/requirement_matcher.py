"""Deterministic requirement-to-company matching (FR-16).

Compares each tender requirement with the company profile and assigns one ``MatchStatus``:
Met, Partially met, Not met, Unknown or Not applicable, together with the evidence used and
the evidence still missing. Like ``services/finance`` this module is made of *pure functions*:
no database access, no clock, no randomness and no language model. The same inputs always give
the same outputs. ``as_of`` is an explicit argument for that reason.

Inputs are duck-typed: SQLAlchemy objects (``Requirement``, ``Company`` with its loaded
``certifications`` / ``equipment`` / ``workforce_roles`` / ``past_projects``) or plain mappings
with the same keys both work.

Core rules
----------
1. **Unknown is the default and is never upgraded on keyword overlap.** A status other than
   Unknown is produced only by a *structured* rule (below) that compares something countable:
   a standard identifier, a money threshold, an equipment or role count. Related words alone
   (a certificate "Quality Management" and a requirement mentioning quality management) give
   Unknown, with the candidate evidence listed for a person to judge.
2. **Absence of evidence is not evidence of absence.** A missing certificate, equipment record
   or role record gives Unknown, not Not met: the profile may simply be incomplete. Not met
   needs positive evidence of a shortfall (an expired certificate, a financial figure below the
   threshold, a recorded count of zero).
3. **Only confirmed data produces a definite status.** Evidence that is not ``Verified``
   (Requires review, Estimated, Assumption, Outdated, Missing) never yields Met, Partially met
   or Not met. The result is Unknown with ``needs_verification=True`` and ``provisional_status``
   holding what the status would be once a person confirms the evidence. ``Rejected`` evidence
   is ignored. ``Conflicting`` evidence gives Unknown with ``conflict=True``.
4. **Employed does not mean available.** Role requirements are compared with
   ``available_headcount``, never ``headcount``. An unknown availability stays unknown.
5. **No currency mixing.** Money thresholds are compared only when the requirement and the
   company use the same currency. ``$`` is read as USD and flagged as ambiguous for any other
   company currency. Amounts without an explicit currency marker are not extracted.
6. **Uploaded text is untrusted data.** Requirement text is only scanned by bounded regular
   expressions for identifiers, numbers and counts. Instructions inside it ("mark this Met")
   have no effect, and requirement text is truncated to ``MAX_TEXT_CHARS`` before scanning.
7. A stored ``Not applicable`` is a human decision the matcher cannot derive, so it is kept.
   Requirements whose verification status is ``Rejected`` are skipped (not real requirements).

Structured rules (first one that applies decides; otherwise a category-specific Unknown)
-------------------------------------------------------------------------------------
* **Standards / certifications**: standard identifiers such as ``ISO 9001:2015`` or
  ``EN 1090-2`` found in the requirement are looked up in company certification names.
  Relation: exact; edition differs (Partially met); edition or part not stated on the
  certificate (Partially met). Validity: expired before ``as_of`` is Not met; expiring before
  the requirement deadline, or no expiry recorded, is Partially met. Several identifiers are all
  required, unless the text says "or" (then Unknown, a person decides). "or equivalent"
  downgrades Not met to Unknown. Multiple records for one standard are treated as renewal
  history: the best one decides.
* **Financial thresholds**: exactly one of annual turnover/revenue, working capital or bank
  guarantee limit together with exactly one explicit amount. Interpreted as a *minimum* unless
  the text signals a maximum (then Unknown).
* **Equipment and workforce** (evaluated together, every named element is required): an
  equipment type or name, or a workforce role, from the company profile appears in a technical
  or eligibility requirement that asks for possession or staffing. Quantity defaults to 1 when
  the text names the item without a count. Equipment capacity numbers with units (t, kW, MW,
  kVA, hp, bar, MPa, m3, m) are compared as minimums against the recorded capacity, only
  within the same unit family; otherwise capacity stays unconfirmed (Partially met at best).
  A more specific requirement ("tower crane") than the recorded type ("crane") is capped at
  Partially met. Roles are compared with ``available_headcount``; qualification or experience
  wording ("10 years", "certified") caps the result at Partially met because the profile
  records capacity per role, not qualifications.
* **Past-project experience**: always Unknown. Whether a project is *similar* is a human
  judgement; the result lists how many recorded projects satisfy the numeric criteria (value,
  recent-years window) as candidates.

``apply_match_result`` writes a result onto a ``Requirement`` row without ever overwriting a
human-reviewed status (see its docstring).
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app.models.enums import MatchStatus, RequirementCategory, VerificationStatus

MATCHER_VERSION = "matcher-1.0.0"
MAX_TEXT_CHARS = 4000  # requirement text is untrusted; scan at most this much of it
MAX_EVIDENCE_REFS = 10

_MET = MatchStatus.MET
_PARTIAL = MatchStatus.PARTIALLY_MET
_NOT_MET = MatchStatus.NOT_MET
_UNKNOWN = MatchStatus.UNKNOWN
_NOT_APPLICABLE = MatchStatus.NOT_APPLICABLE

_VERIFIED = VerificationStatus.VERIFIED.value
_REJECTED = VerificationStatus.REJECTED.value
_CONFLICTING = VerificationStatus.CONFLICTING.value
_MISSING = VerificationStatus.MISSING.value
_REVIEW = VerificationStatus.REQUIRES_REVIEW.value

# How good a *definite* result is. Unknown is deliberately absent: it is never "better".
_RANK = {_NOT_MET: 1, _PARTIAL: 2, _MET: 3}

_CAT = RequirementCategory


# --------------------------------------------------------------------------- result types
@dataclass(frozen=True)
class EvidenceRef:
    """One company record that was consulted. Shown next to the status as a source chip."""

    kind: str  # "certification" | "equipment" | "workforce_role" | "past_project" | "company_field"
    record_id: Optional[int]
    label: str
    verification_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "record_id": self.record_id,
            "label": self.label,
            "verification_status": self.verification_status,
        }


@dataclass(frozen=True)
class MatchResult:
    """Outcome for one requirement.

    ``status`` is what may be stored. ``provisional_status`` is only set when ``status`` is
    Unknown *because the evidence is not yet confirmed*: it is what the status would be if a
    person confirmed that evidence. It must never be shown as the status.
    """

    requirement_id: Optional[int]
    requirement_code: str
    status: MatchStatus
    rule: str
    evidence_summary: Optional[str] = None  # evidence used (stored in Requirement.evidence_summary)
    missing_evidence: Optional[str] = None  # what would close the gap (Requirement.missing_evidence)
    provisional_status: Optional[MatchStatus] = None
    needs_verification: bool = False
    conflict: bool = False
    evidence: tuple[EvidenceRef, ...] = ()
    notes: tuple[str, ...] = ()
    matcher_version: str = MATCHER_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "requirement_code": self.requirement_code,
            "status": self.status.value,
            "rule": self.rule,
            "evidence_summary": self.evidence_summary,
            "missing_evidence": self.missing_evidence,
            "provisional_status": self.provisional_status.value if self.provisional_status else None,
            "needs_verification": self.needs_verification,
            "conflict": self.conflict,
            "evidence": [e.to_dict() for e in self.evidence],
            "notes": list(self.notes),
            "matcher_version": self.matcher_version,
        }


@dataclass(frozen=True)
class StandardId:
    """A standard identifier such as ISO 9001:2015 (key ``ISO 9001``, year ``2015``)."""

    key: str
    part: Optional[str] = None
    year: Optional[str] = None

    @property
    def label(self) -> str:
        text = self.key + (f"-{self.part}" if self.part else "")
        return text + (f":{self.year}" if self.year else "")


@dataclass(frozen=True)
class MoneyAmount:
    value: Decimal
    currency: str  # ISO code
    ambiguous_symbol: bool = False  # "$" alone: read as USD but not certain
    raw: str = ""


@dataclass(frozen=True)
class FinancialThreshold:
    """A financial requirement reduced to metric + amount (always read as a minimum)."""

    metric: str  # Company field: annual_revenue | working_capital | bank_guarantee_limit
    amount: MoneyAmount


# --------------------------------------------------------------------------- small helpers
def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _value(v: Any) -> Any:
    return getattr(v, "value", v)


def _seq(obj: Any, name: str) -> list[Any]:
    items = _get(obj, name)
    return list(items) if items else []


def _vstatus(obj: Any) -> str:
    status = _value(_get(obj, "verification_status"))
    return str(status) if status else _REVIEW


def _to_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _clean(text: Any) -> str:
    """Untrusted text: str, bounded, control characters replaced by spaces."""
    raw = "" if text is None else str(text)
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", raw[:MAX_TEXT_CHARS])


def _clip(text: Any, limit: int = 120) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _code_key(code: str) -> tuple:
    """Natural-sort key ("REQ-2" < "REQ-10"). Parts are tagged so digits and text never compare."""
    return tuple(
        (0, int(p), "") if p.isdigit() else (1, 0, p.lower())
        for p in re.split(r"(\d+)", str(code or ""))
        if p
    )


def _field_status(company: Any, field_name: str) -> str:
    """Mirror of ``Company.get_field_status`` that also works for mappings."""
    entry = (_get(company, "field_verification") or {}).get(field_name)
    if isinstance(entry, Mapping) and entry.get("status"):
        return str(entry["status"])
    current = _get(company, field_name)
    return _MISSING if current in (None, "", []) else _REVIEW


def _money_text(value: Decimal, currency: str) -> str:
    return f"{currency} {value:,.2f}"


# ------------------------------------------------------------------------- text utilities
_WORD_RE = re.compile(r"[a-z0-9]+")


def _stem(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _tokens(text: str) -> list[str]:
    return [_stem(t) for t in _WORD_RE.findall(text.lower())]


def _find(tokens: list[str], phrase: list[str]) -> Optional[int]:
    n = len(phrase)
    if n == 0:
        return None
    for i in range(len(tokens) - n + 1):
        if tokens[i : i + n] == phrase:
            return i
    return None


_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}
_COUNT_WORD_ALT = "|".join(_NUMBER_WORDS)


def _as_count(token: str) -> Optional[int]:
    if token.isdigit() and len(token) <= 4:
        return int(token)
    return _NUMBER_WORDS.get(token)


_UNIT_TOKENS = frozenset(
    {"t", "ton", "tonne", "kw", "mw", "kva", "hp", "bar", "mpa", "m3", "m", "year", "month"}
)
_COUNT_BOUNDARY = frozenset({"and", "or", "with", "plus", "including", "excluding"})
_NOT_A_MODIFIER = frozenset(
    {
        "a", "an", "the", "of", "minimum", "min", "least", "at", "x", "no", "nos", "unit", "set",
        "number", "more", "than", "own", "have", "has", "provide", "available", "with", "for",
        "and", "or", "plus", "including", "must", "shall", "should", "to", "be", "by", "its",
        "their", "our", "company", "contractor", "bidder", "tenderer", "per", "each", "all",
        "any", "some", "sufficient", "adequate", "suitable", "required", "valid", "current",
        "key", "named", "experience", "experienced", "qualified", "certified", "licensed",
        "licenced", "registered", "chartered", "competent", "skilled", "dedicated", "full", "time",
    }
)
_GENERIC_TERMS = frozenset(
    {"equipment", "machine", "machinery", "tool", "vehicle", "plant", "item", "other", "general"}
)


def _required_count(tokens: list[str], idx: int) -> tuple[int, bool]:
    """Count stated just before the phrase at ``idx``; default 1 (the item is named at all)."""
    for j in range(idx - 1, max(idx - 6, -1), -1):
        token = tokens[j]
        if token in _COUNT_BOUNDARY:
            break
        count = _as_count(token)
        if count is not None and not (j + 1 < len(tokens) and tokens[j + 1] in _UNIT_TOKENS):
            return count, True
    return 1, False


def _modifier_before(tokens: list[str], idx: int) -> Optional[str]:
    """A word that makes the requirement more specific than the matched company phrase."""
    if idx <= 0:
        return None
    token = tokens[idx - 1]
    if token in _NOT_A_MODIFIER or token in _COUNT_BOUNDARY or _as_count(token) is not None:
        return None
    if token in _UNIT_TOKENS or token.isdigit():
        return None
    return token


# -------------------------------------------------------------------- standard identifiers
_STD_RE = re.compile(
    r"\b(ISO(?:/IEC)?|IEC|OHSAS|IATF|ASME|API|AWS|BS|EN|DIN|NFPA|SANS|ASTM)\s*[-/]?\s*"
    r"(\d{3,6})(?:-(\d{1,2}))?(?::(\d{4}))?(?!\d)",
    re.IGNORECASE,
)
# Short prefixes that are ordinary words in lower case ("en", "bs", "api") must be upper case.
_UPPERCASE_ONLY = frozenset({"EN", "BS", "API", "AWS", "DIN"})


def extract_standard_ids(text: Any) -> list[StandardId]:
    """Standard identifiers in ``text`` in order of appearance, without duplicates."""
    found: list[StandardId] = []
    for m in _STD_RE.finditer(_clean(text)):
        prefix = m.group(1)
        if prefix.upper() in _UPPERCASE_ONLY and prefix != prefix.upper():
            continue
        key_prefix = "ISO" if prefix.upper().startswith("ISO") else prefix.upper()
        sid = StandardId(f"{key_prefix} {m.group(2)}", m.group(3), m.group(4))
        if sid not in found:
            found.append(sid)
    return found


def _standard_relation(required: StandardId, held: StandardId) -> Optional[str]:
    """How a certificate's identifier relates to the required one (None = different standard)."""
    if required.key != held.key:
        return None
    if required.part and held.part and required.part != held.part:
        return None
    if required.part and not held.part:
        return "unconfirmed"
    if required.year and held.year and required.year != held.year:
        return "edition_mismatch"
    if required.year and not held.year:
        return "unconfirmed"
    return "exact"


# ------------------------------------------------------------------------- money parsing
_AMOUNT = r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_MAG = r"thousand|million|billion|lakhs?|lacs?|crores?|mn|bn|k|m"
_CODES = r"USD|EUR|GBP|INR|AUD|CAD|NZD|SGD|AED|SAR|ZAR|CHF|CNY|JPY"
_MONEY_RE = re.compile(
    rf"(?P<pre>US\$|\$|€|£|₹|\bRs\.?|\b(?:{_CODES})\b)\s*(?P<amt1>{_AMOUNT})(?:\s*(?P<mag1>{_MAG})\b)?"
    rf"|(?P<amt2>{_AMOUNT})(?:\s*(?P<mag2>{_MAG}))?\s*(?P<post>\b(?:{_CODES})\b)",
    re.IGNORECASE,
)
_MAGNITUDE = {
    "thousand": Decimal("1e3"), "k": Decimal("1e3"), "million": Decimal("1e6"),
    "m": Decimal("1e6"), "mn": Decimal("1e6"), "billion": Decimal("1e9"), "bn": Decimal("1e9"),
    "lakh": Decimal("1e5"), "lakhs": Decimal("1e5"), "lac": Decimal("1e5"), "lacs": Decimal("1e5"),
    "crore": Decimal("1e7"), "crores": Decimal("1e7"),
}
_SYMBOL_CODE = {"us$": "USD", "$": "USD", "€": "EUR", "£": "GBP", "₹": "INR", "rs": "INR", "rs.": "INR"}


def extract_money_amounts(text: Any) -> list[MoneyAmount]:
    """Amounts with an explicit currency marker. Unmarked numbers are never taken as money."""
    out: list[MoneyAmount] = []
    for m in _MONEY_RE.finditer(_clean(text)):
        marker = (m.group("pre") or m.group("post")).strip()
        amount_text = m.group("amt1") or m.group("amt2")
        magnitude = (m.group("mag1") or m.group("mag2") or "").lower()
        try:
            value = Decimal(amount_text.replace(",", ""))
        except InvalidOperation:  # pragma: no cover - the regex only admits digits
            continue
        value *= _MAGNITUDE.get(magnitude, Decimal(1))
        if value <= 0:
            continue
        lowered = marker.lower()
        currency = _SYMBOL_CODE.get(lowered, marker.upper())
        item = MoneyAmount(value, currency, ambiguous_symbol=(lowered == "$"), raw=m.group(0).strip())
        if all((a.value, a.currency) != (item.value, item.currency) for a in out):
            out.append(item)
    return out


_FIN_METRICS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("annual_revenue", ("turnover", "annual revenue", "annual sale", "revenue"), "annual turnover"),
    ("working_capital", ("working capital",), "working capital"),
    ("bank_guarantee_limit", ("bank guarantee",), "bank guarantee limit"),
)
_FIN_LABEL = {name: label for name, _, label in _FIN_METRICS}
_MIN_PHRASE_RE = re.compile(r"\b(?:not|no)\s+less\s+than\b", re.IGNORECASE)
_MAX_CUE_RE = re.compile(
    r"\b(?:maximum|max|at\s+most|not\s+more\s+than|no\s+more\s+than|not\s+(?:to\s+)?exceed(?:s|ing)?|"
    r"up\s+to|below|under|less\s+than|lower\s+than)\b",
    re.IGNORECASE,
)


def _financial_metrics_in(text: str) -> list[str]:
    tokens = _tokens(text)
    return [name for name, keys, _ in _FIN_METRICS if any(_find(tokens, _tokens(k)) is not None for k in keys)]


def _parse_financial(text: Any) -> tuple[Optional[FinancialThreshold], Optional[str]]:
    """(threshold, None) when unambiguous, else (None, reason)."""
    cleaned = _clean(text)
    metrics = _financial_metrics_in(cleaned)
    if not metrics:
        return None, "no recognised financial metric (turnover, working capital, bank guarantee)"
    if len(metrics) > 1:
        return None, "several financial metrics are named in one requirement"
    amounts = extract_money_amounts(cleaned)
    if not amounts:
        return None, "no amount with an explicit currency was found (percentages and unmarked numbers are not read)"
    if len(amounts) > 1:
        return None, "several different amounts are named in one requirement"
    if _MAX_CUE_RE.search(_MIN_PHRASE_RE.sub(" ", cleaned)):
        return None, "the threshold reads as a maximum; only minimum thresholds are compared"
    return FinancialThreshold(metrics[0], amounts[0]), None


def extract_financial_requirement(text: Any) -> Optional[FinancialThreshold]:
    """Public helper (used by the gap detector to spot contradictory thresholds)."""
    return _parse_financial(text)[0]


# ------------------------------------------------------------------------------- context
_CERT_CUE = re.compile(
    r"\b(?:certif\w*|accredit\w*|registered|registration|hold(?:s|ing)?|licen[cs]\w*|approved)\b",
    re.IGNORECASE,
)
_POSSESSION_CUE = re.compile(
    r"\b(?:own\w*|possess\w*|have|has|provide\w*|equipped|availab\w*|deploy\w*|mobili[sz]\w*|"
    r"operat\w*|minimum|at\s+least|plant|equipment|fleet|machinery)\b",
    re.IGNORECASE,
)
_STAFF_CUE = re.compile(
    r"\b(?:personnel|staff|team|employ\w*|crew|workforce|manpower|resources?|deploy\w*|assign\w*|"
    r"availab\w*|minimum|at\s+least|key|provide\w*|supply|supplied|have|has|hold\w*|nominate\w*|"
    r"appoint\w*|engage\w*)\b",
    re.IGNORECASE,
)
_QUALIFICATION_CUE = re.compile(
    r"\b(?:years?|experience\w*|certified|qualified|licen[cs]ed|registered|chartered|degree|"
    r"diploma|accredited)\b",
    re.IGNORECASE,
)
_ALT_CUE = re.compile(r"\bor\b", re.IGNORECASE)
_EQUIVALENT_CUE = re.compile(r"\bequivalent\b", re.IGNORECASE)
_EXPERIENCE_CUE = re.compile(
    r"\b(?:similar|comparable|previous|completed|relevant)\b[^.]{0,60}?\b(?:projects?|contracts?|assignments?|works?|references?)\b"
    r"|\b(?:track\s+record|experience)\b[^.]{0,60}?\b(?:projects?|contracts?)\b",
    re.IGNORECASE,
)
_PROJECT_COUNT_RE = re.compile(
    rf"\b(\d{{1,3}}|{_COUNT_WORD_ALT})\s+(?:(?:similar|comparable|completed|relevant|previous|successful)\s+){{0,3}}"
    r"(?:projects?|contracts?|assignments?|references?)\b",
    re.IGNORECASE,
)
_PERIOD_RE = re.compile(
    rf"\b(?:last|past|preceding|previous)\s+(\d{{1,2}}|{_COUNT_WORD_ALT})\s+years?\b", re.IGNORECASE
)
_SPEC_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s*(tonnes?|tons?|kva|kw|mw|hp|bar|mpa|m3|m|t)\b", re.IGNORECASE
)
_UNIT_FAMILY = {
    "t": ("mass", Decimal(1)), "ton": ("mass", Decimal(1)), "tons": ("mass", Decimal(1)),
    "tonne": ("mass", Decimal(1)), "tonnes": ("mass", Decimal(1)),
    "kw": ("power", Decimal(1)), "mw": ("power", Decimal(1000)),
    "kva": ("apparent power", Decimal(1)), "hp": ("horsepower", Decimal(1)),
    "bar": ("pressure", Decimal(1)), "mpa": ("pressure", Decimal(10)),
    "m3": ("volume", Decimal(1)), "m": ("length", Decimal(1)),
}


@dataclass(frozen=True)
class _Ctx:
    requirement: Any
    text: str
    tokens: list[str]
    category: RequirementCategory
    company: Any
    as_of: date
    deadline: Optional[date]


@dataclass
class _Item:
    """Result for one element of a requirement (one standard, equipment type, role, ...)."""

    final: MatchStatus
    provisional: Optional[MatchStatus] = None
    needs_verification: bool = False
    conflict: bool = False
    evidence: list[EvidenceRef] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _gate(s_verified: Optional[MatchStatus], s_all: MatchStatus) -> tuple[MatchStatus, Optional[MatchStatus], bool]:
    """Apply the verification rule. Returns (final, provisional, needs_verification).

    A definite status is only returned when verified evidence is at least as good as *all*
    evidence; unverified evidence that could change the answer leaves the result Unknown.
    """
    if s_all is _UNKNOWN:
        return _UNKNOWN, None, False
    if s_verified is not None and s_verified is not _UNKNOWN and _RANK[s_verified] >= _RANK[s_all]:
        return s_verified, None, False
    return _UNKNOWN, s_all, True


def _combine_all(statuses: list[MatchStatus]) -> MatchStatus:
    """Every element is required: one failure fails the whole, one unknown leaves it unknown."""
    if _NOT_MET in statuses:
        return _NOT_MET
    if _UNKNOWN in statuses:
        return _UNKNOWN
    if _PARTIAL in statuses:
        return _PARTIAL
    return _MET


def _combine_items(items: list[_Item]) -> tuple[MatchStatus, Optional[MatchStatus], bool, bool]:
    """(status, provisional, needs_verification, conflict) for a set of required elements."""
    if any(i.conflict for i in items):
        return _UNKNOWN, None, any(i.needs_verification for i in items), True
    status = _combine_all([i.final for i in items])
    provisional = None
    if status is _UNKNOWN:
        candidate = _combine_all([i.provisional or i.final for i in items])
        provisional = candidate if candidate is not _UNKNOWN else None
    return status, provisional, any(i.needs_verification for i in items), False


def _result(
    ctx: _Ctx,
    status: MatchStatus,
    rule: str,
    *,
    items: Iterable[_Item] = (),
    provisional: Optional[MatchStatus] = None,
    needs_verification: bool = False,
    conflict: bool = False,
    extra_missing: Iterable[str] = (),
    extra_notes: Iterable[str] = (),
) -> MatchResult:
    items = list(items)
    lines = [line for i in items for line in i.lines]
    missing = [m for i in items for m in i.missing] + list(extra_missing)
    notes = [n for i in items for n in i.notes] + list(extra_notes)
    evidence = tuple(e for i in items for e in i.evidence)[:MAX_EVIDENCE_REFS]
    if status is _MET:
        missing = []
    if conflict:
        notes.append("Conflicting company records: a person must resolve the conflict before matching.")
        missing.append("Resolution of the conflicting company records")
    req = ctx.requirement
    return MatchResult(
        requirement_id=_get(req, "id"),
        requirement_code=str(_get(req, "code") or ""),
        status=status,
        rule=rule,
        evidence_summary="; ".join(lines) or None,
        missing_evidence="; ".join(dict.fromkeys(missing)) or None,
        provisional_status=provisional,
        needs_verification=needs_verification,
        conflict=conflict,
        evidence=evidence,
        notes=tuple(dict.fromkeys(notes)),
    )


# ------------------------------------------------------------------ rule: certifications
_VALIDITY_RANK = {"valid": 0, "expires_before_deadline": 1, "no_expiry": 2, "expired": 3}


def _cert_status(relation: str, validity: str) -> MatchStatus:
    if validity == "expired":
        return _NOT_MET
    if relation == "exact" and validity == "valid":
        return _MET
    return _PARTIAL


def _eval_standard(sid: StandardId, ctx: _Ctx) -> _Item:
    candidates: list[tuple[Any, str, str, MatchStatus, str, Optional[date]]] = []
    for cert in _seq(ctx.company, "certifications"):
        vstatus = _vstatus(cert)
        if vstatus == _REJECTED:
            continue
        relation = None
        for held in extract_standard_ids(_get(cert, "name")):
            relation = _standard_relation(sid, held)
            if relation:
                break
        if not relation:
            continue
        expiry = _to_date(_get(cert, "expiry_date"))
        if expiry is None:
            validity = "no_expiry"
        elif expiry < ctx.as_of:
            validity = "expired"
        elif ctx.deadline and expiry < ctx.deadline:
            validity = "expires_before_deadline"
        else:
            validity = "valid"
        candidates.append((cert, vstatus, relation, _cert_status(relation, validity), validity, expiry))

    if not candidates:
        return _Item(
            _UNKNOWN,
            missing=[f"Certificate for {sid.label} (name, issuing body, expiry date)"],
            notes=[f"No company certification matching {sid.label} was found; this is not evidence that none is held."],
        )

    def order(c: tuple) -> tuple:
        cert, vstatus, relation, status, validity, expiry = c
        return (
            -_RANK[status],
            _VALIDITY_RANK[validity],
            -(expiry.toordinal() if expiry else 0),
            _get(cert, "id") or 0,
        )

    verified = sorted((c for c in candidates if c[1] == _VERIFIED), key=order)
    everything = sorted(candidates, key=order)
    best_all, best_verified = everything[0], (verified[0] if verified else None)
    final, provisional, needs = _gate(best_verified[3] if best_verified else None, best_all[3])
    shown = best_verified if final is not _UNKNOWN else best_all

    cert, vstatus, relation, status, validity, expiry = shown
    name = _clip(_get(cert, "name"))
    item = _Item(final, provisional, needs)
    item.conflict = any(c[1] == _CONFLICTING for c in candidates)
    item.evidence.append(EvidenceRef("certification", _get(cert, "id"), name, vstatus))
    detail = f"Certification '{name}' ({vstatus}"
    if expiry:
        detail += f", expires {expiry.isoformat()}"
    item.lines.append(detail + ")")
    if validity == "expired":
        item.notes.append(f"{sid.label}: certificate expired on {expiry.isoformat()}.")
        item.missing.append(f"Current certificate for {sid.label} (the recorded one has expired)")
    elif validity == "expires_before_deadline":
        item.notes.append(
            f"{sid.label}: certificate expires {expiry.isoformat()}, before the requirement deadline "
            f"{ctx.deadline.isoformat()}."
        )
        item.missing.append(f"Evidence of renewal for {sid.label}")
    elif validity == "no_expiry":
        item.notes.append(f"{sid.label}: no expiry date is recorded, so validity cannot be confirmed.")
        item.missing.append(f"Expiry date of the {sid.label} certificate")
    if relation == "edition_mismatch":
        item.notes.append(f"{sid.label}: the certificate names a different edition than the one required.")
        item.missing.append(f"Certificate for the required edition of {sid.label}")
    elif relation == "unconfirmed":
        item.notes.append(f"{sid.label}: edition or part is not stated on the certificate.")
        item.missing.append(f"Edition/part stated on the {sid.label} certificate")
    if needs:
        item.missing.append(f"Confirmation by a person of the {sid.label} certificate record")
    return item


def _rule_certification(ctx: _Ctx) -> Optional[MatchResult]:
    ids = extract_standard_ids(ctx.text)
    if not ids:
        return None
    applies = ctx.category is _CAT.CERTIFICATION or (
        ctx.category in (_CAT.ELIGIBILITY, _CAT.TECHNICAL, _CAT.LEGAL_CONTRACTUAL, _CAT.OTHER)
        and _CERT_CUE.search(ctx.text)
    )
    if not applies:
        return None
    items = [_eval_standard(sid, ctx) for sid in ids]
    if len(ids) > 1 and _ALT_CUE.search(ctx.text):
        # "ISO 9001 or ISO 14001": which combination is acceptable is a human reading.
        return _result(
            ctx,
            _UNKNOWN,
            "certification",
            items=[_Item(_UNKNOWN, evidence=i.evidence, lines=i.lines) for i in items],
            extra_missing=["A person must decide which of the alternative standards is acceptable"],
            extra_notes=["The requirement lists alternatives ('or'); each standard was looked up but not combined."],
        )
    status, provisional, needs, conflict = _combine_items(items)
    notes: list[str] = []
    if status is _NOT_MET and _EQUIVALENT_CUE.search(ctx.text):
        status, notes = _UNKNOWN, ["The requirement allows an equivalent certificate, so a shortfall is not definite."]
    return _result(
        ctx, status, "certification", items=items, provisional=provisional,
        needs_verification=needs, conflict=conflict, extra_notes=notes,
    )


# ------------------------------------------------------------------- rule: financial
_FIN_APPLIES = (_CAT.FINANCIAL, _CAT.ELIGIBILITY)


def _rule_financial(ctx: _Ctx) -> Optional[MatchResult]:
    if ctx.category not in _FIN_APPLIES or not _financial_metrics_in(ctx.text):
        return None
    threshold, reason = _parse_financial(ctx.text)
    if threshold is None:
        return _result(
            ctx, _UNKNOWN, "financial",
            extra_missing=["A single, explicit financial threshold with its currency, confirmed by a person"],
            extra_notes=[f"Threshold not machine-readable: {reason}."],
        )
    label = _FIN_LABEL[threshold.metric]
    amount = threshold.amount
    need = _money_text(amount.value, amount.currency)
    value = _get(ctx.company, threshold.metric)
    vstatus = _field_status(ctx.company, threshold.metric)
    if ctx.company is None or value is None or vstatus in (_REJECTED, _MISSING):
        return _result(
            ctx, _UNKNOWN, "financial",
            extra_missing=[f"Company {label} (not recorded or rejected), compared with the required {need}"],
        )
    try:
        value = Decimal(str(value))
    except InvalidOperation:
        return _result(ctx, _UNKNOWN, "financial", extra_missing=[f"A valid company {label} figure"])

    currency = str(_get(ctx.company, "currency") or "").upper()
    if currency != amount.currency:
        return _result(
            ctx, _UNKNOWN, "financial",
            extra_missing=[f"An explicit currency conversion: the requirement is in {amount.currency}, the company in {currency or 'an unknown currency'}"],
            extra_notes=["Currencies are never mixed without an explicit conversion."],
        )
    notes = []
    if amount.ambiguous_symbol and currency != "USD":
        return _result(ctx, _UNKNOWN, "financial", extra_missing=["Which currency the '$' in the requirement means"])
    if amount.ambiguous_symbol:
        notes.append("The requirement uses '$', read as USD.")

    provisional = _MET if value >= amount.value else _NOT_MET
    item = _Item(_UNKNOWN)
    ref = EvidenceRef("company_field", None, f"{label}: {_money_text(value, currency)}", vstatus)
    item.evidence.append(ref)
    item.lines.append(f"Company {label} {_money_text(value, currency)} ({vstatus}) against required {need}")
    if vstatus == _CONFLICTING:
        item.conflict = True
        return _result(ctx, _UNKNOWN, "financial", items=[item], conflict=True, extra_notes=notes)
    final, prov, needs = _gate(provisional if vstatus == _VERIFIED else None, provisional)
    item.final, item.provisional, item.needs_verification = final, prov, needs
    if needs:
        item.missing.append(f"Confirmation by a person of the company {label} figure")
    if final is _NOT_MET:
        shortfall = amount.value - value
        item.notes.append(f"Shortfall of {_money_text(shortfall, currency)} against the threshold.")
        item.missing.append(f"Higher {label} evidence, or a partner/guarantor that closes the shortfall")
    return _result(
        ctx, final, "financial", items=[item], provisional=prov,
        needs_verification=needs, extra_notes=notes,
    )


# -------------------------------------------------------- rules: equipment and workforce
def _phrases(*names: Any) -> list[list[str]]:
    out: list[list[str]] = []
    for name in names:
        toks = _tokens(_clean(name))
        if toks and not all(t in _GENERIC_TERMS for t in toks) and len(" ".join(toks)) >= 3 and toks not in out:
            out.append(toks)
    return out


def _specs(text: str) -> list[tuple[str, Decimal]]:
    found = []
    for m in _SPEC_RE.finditer(text):
        number = Decimal(m.group(1).replace(",", "") + (m.group(2) or ""))
        family, factor = _UNIT_FAMILY[m.group(3).lower()]
        found.append((family, number * factor))
    return found


def _capacity_ok(required: list[tuple[str, Decimal]], capacity: Any) -> Optional[bool]:
    """True/False when the recorded capacity can be compared, None when it cannot."""
    held = _specs(_clean(capacity))
    verdicts: list[Optional[bool]] = []
    for family, need in required:
        values = [v for f, v in held if f == family]
        verdicts.append(None if not values else max(values) >= need)
    if any(v is False for v in verdicts):
        return False
    return None if any(v is None for v in verdicts) else True


def _cap_partial(status: Optional[MatchStatus]) -> Optional[MatchStatus]:
    return _PARTIAL if status is _MET else status


def _count_status(have: int, need: int) -> MatchStatus:
    if have >= need:
        return _MET
    return _NOT_MET if have == 0 else _PARTIAL


def _eval_equipment(phrase: list[str], idx: int, ctx: _Ctx, specs: list[tuple[str, Decimal]], single: bool) -> _Item:
    need, stated = _required_count(ctx.tokens, idx)
    modifier = _modifier_before(ctx.tokens, idx)
    shown = " ".join(phrase)
    hits = []
    for item in _seq(ctx.company, "equipment"):
        vstatus = _vstatus(item)
        if vstatus == _REJECTED:
            continue
        if phrase in _phrases(_get(item, "equipment_type"), _get(item, "name")):
            hits.append((item, vstatus))
    out = _Item(_UNKNOWN)
    out.conflict = any(v == _CONFLICTING for _, v in hits)

    def status_for(rows: list[tuple[Any, str]]) -> Optional[MatchStatus]:
        if not rows:
            return None
        total = sum(int(_get(i, "quantity") or 0) for i, _ in rows)
        if specs and single:
            # Only items whose recorded capacity is shown to meet the specification count
            # towards "Met". Items present but not shown to qualify keep it at Partially met.
            qualified = sum(
                int(_get(i, "quantity") or 0) for i, _ in rows if _capacity_ok(specs, _get(i, "capacity")) is True
            )
            if qualified >= need:
                result = _MET
            elif total == 0:
                result = _NOT_MET
            else:
                result = _PARTIAL
        else:
            result = _count_status(total, need)
        if modifier or (specs and not single):
            result = _cap_partial(result)
        return result

    s_all = status_for(hits)
    if s_all is None:
        out.missing.append(f"Equipment record for '{shown}' (type, quantity, capacity)")
        out.notes.append(f"No company equipment matching '{shown}' was found; this is not evidence that none is owned.")
        return out
    s_ver = status_for([h for h in hits if h[1] == _VERIFIED])
    out.final, out.provisional, out.needs_verification = _gate(s_ver, s_all)
    total_q = sum(int(_get(i, "quantity") or 0) for i, _ in hits)
    for i, v in hits:
        out.evidence.append(EvidenceRef("equipment", _get(i, "id"), _clip(_get(i, "name")), v))
    out.lines.append(
        "Equipment: " + ", ".join(f"{_clip(_get(i, 'name'))} x{int(_get(i, 'quantity') or 0)} ({v})" for i, v in hits)
        + f"; required {need}{'' if stated else ' (assumed: no count stated)'}"
    )
    if modifier:
        out.notes.append(f"Requirement says '{modifier} {shown}' but the profile records '{shown}'; confirm the type.")
        out.missing.append(f"Confirmation that the recorded '{shown}' is of the required type")
    if specs:
        if single:
            out.missing.append("Recorded capacity that meets the required specification")
        else:
            out.notes.append("Several equipment types and capacity figures: capacity cannot be assigned to one type.")
            out.missing.append("Per-item capacity evidence")
    if total_q < need and out.final is not _MET:
        out.missing.append(f"Evidence of {need - total_q} more '{shown}' (owned, leased or committed)")
    if out.needs_verification:
        out.missing.append("Confirmation by a person of the equipment records")
    return out


def _equipment_items(ctx: _Ctx) -> list[_Item]:
    if not _POSSESSION_CUE.search(ctx.text):
        return []
    found: dict[tuple[str, ...], int] = {}
    for item in _seq(ctx.company, "equipment"):
        if _vstatus(item) == _REJECTED:
            continue
        for p in _phrases(_get(item, "equipment_type"), _get(item, "name")):
            idx = _find(ctx.tokens, p)
            if idx is not None:
                found.setdefault(tuple(p), idx)
                break
    specs = _specs(ctx.text)
    return [
        _eval_equipment(list(p), idx, ctx, specs, len(found) == 1)
        for p, idx in sorted(found.items(), key=lambda kv: kv[1])
    ]


def _eval_role(phrase: list[str], idx: int, ctx: _Ctx, qualified_wording: bool) -> _Item:
    need, stated = _required_count(ctx.tokens, idx)
    modifier = _modifier_before(ctx.tokens, idx)
    shown = " ".join(phrase)
    hits = []
    for role in _seq(ctx.company, "workforce_roles"):
        vstatus = _vstatus(role)
        if vstatus != _REJECTED and phrase in _phrases(_get(role, "role")):
            hits.append((role, vstatus))
    out = _Item(_UNKNOWN)
    out.conflict = any(v == _CONFLICTING for _, v in hits)

    def status_for(rows: list[tuple[Any, str]]) -> Optional[MatchStatus]:
        if not rows:
            return None
        known = [int(_get(r, "available_headcount")) for r, _ in rows if _get(r, "available_headcount") is not None]
        unknown_exists = len(known) < len(rows)
        have = sum(known)
        if have >= need:
            result = _MET
        elif unknown_exists:
            result = _UNKNOWN
        else:
            result = _count_status(have, need)
        if result is not _UNKNOWN and (modifier or qualified_wording):
            result = _cap_partial(result)
        return result

    s_all = status_for(hits)
    if s_all is None:
        out.missing.append(f"Workforce role '{shown}' with its available headcount")
        out.notes.append(f"No company role matching '{shown}' was found; this is not evidence that none is employed.")
        return out
    s_ver = status_for([h for h in hits if h[1] == _VERIFIED])
    out.final, out.provisional, out.needs_verification = _gate(s_ver, s_all)
    for r, v in hits:
        avail = _get(r, "available_headcount")
        out.evidence.append(EvidenceRef("workforce_role", _get(r, "id"), _clip(_get(r, "role")), v))
        out.lines.append(
            f"Role '{_clip(_get(r, 'role'))}': employed {_get(r, 'headcount')}, available "
            f"{'unknown' if avail is None else avail} ({v}); required {need}"
            f"{'' if stated else ' (assumed: no count stated)'}"
        )
    if any(_get(r, "available_headcount") is None for r, _ in hits):
        out.missing.append(f"Available headcount for '{shown}' (employed does not mean available)")
        out.notes.append("Employed headcount is not availability; unknown availability stays unknown.")
    if modifier:
        out.notes.append(f"Requirement says '{modifier} {shown}' but the profile records '{shown}'; confirm seniority/type.")
        out.missing.append(f"Confirmation that the recorded '{shown}' roles match the required seniority/type")
    if qualified_wording:
        out.missing.append("Evidence of the required qualifications or experience (the profile records role capacity only)")
    if out.needs_verification:
        out.missing.append("Confirmation by a person of the workforce records")
    return out


def _workforce_items(ctx: _Ctx) -> list[_Item]:
    if not _STAFF_CUE.search(ctx.text):
        return []
    found: dict[tuple[str, ...], int] = {}
    for role in _seq(ctx.company, "workforce_roles"):
        if _vstatus(role) == _REJECTED:
            continue
        for p in _phrases(_get(role, "role")):
            idx = _find(ctx.tokens, p)
            if idx is not None:
                found.setdefault(tuple(p), idx)
    qualified = bool(_QUALIFICATION_CUE.search(ctx.text))
    return [
        _eval_role(list(p), idx, ctx, qualified)
        for p, idx in sorted(found.items(), key=lambda kv: kv[1])
    ]


def _rule_capability(ctx: _Ctx) -> Optional[MatchResult]:
    """Equipment and workforce elements of one requirement are all required, so they are
    evaluated together ("a project manager and a tower crane" needs both)."""
    if ctx.category not in (_CAT.TECHNICAL, _CAT.ELIGIBILITY):
        return None
    equipment, roles = _equipment_items(ctx), _workforce_items(ctx)
    items = equipment + roles
    if not items:
        return None
    status, provisional, needs, conflict = _combine_items(items)
    rule = "equipment+workforce" if equipment and roles else ("equipment" if equipment else "workforce")
    return _result(
        ctx, status, rule, items=items, provisional=provisional,
        needs_verification=needs, conflict=conflict,
    )


# --------------------------------------------------------------- rule: past-project experience
def _years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February
        return day.replace(year=day.year - years, day=28)


def _rule_experience(ctx: _Ctx) -> Optional[MatchResult]:
    if ctx.category not in (_CAT.TECHNICAL, _CAT.ELIGIBILITY, _CAT.OTHER) or not _EXPERIENCE_CUE.search(ctx.text):
        return None
    count_m = _PROJECT_COUNT_RE.search(ctx.text)
    need = None
    if count_m:
        raw = count_m.group(1).lower()
        need = int(raw) if raw.isdigit() else _NUMBER_WORDS[raw]
    period_m = _PERIOD_RE.search(ctx.text)
    since = None
    if period_m:
        raw = period_m.group(1).lower()
        since = _years_before(ctx.as_of, int(raw) if raw.isdigit() else _NUMBER_WORDS[raw])
    amounts = extract_money_amounts(ctx.text)
    min_value = amounts[0] if len(amounts) == 1 else None

    verified, unverified = [], []
    for project in _seq(ctx.company, "past_projects"):
        vstatus = _vstatus(project)
        if vstatus == _REJECTED:
            continue
        done = _to_date(_get(project, "completion_date"))
        if since and (done is None or done < since):
            continue
        if min_value:
            value = _get(project, "contract_value")
            if value is None or str(_get(project, "currency") or "").upper() != min_value.currency:
                continue
            if Decimal(str(value)) < min_value.value:
                continue
        (verified if vstatus == _VERIFIED else unverified).append((project, vstatus))

    item = _Item(_UNKNOWN)
    for project, vstatus in (verified + unverified)[:MAX_EVIDENCE_REFS]:
        item.evidence.append(EvidenceRef("past_project", _get(project, "id"), _clip(_get(project, "title")), vstatus))
    criteria = []
    if since:
        criteria.append(f"completed since {since.isoformat()}")
    if min_value:
        criteria.append(f"contract value of at least {_money_text(min_value.value, min_value.currency)}")
    desc = " and ".join(criteria) or "no numeric criteria"
    item.lines.append(
        f"{len(verified)} verified and {len(unverified)} unverified recorded past project(s) meet the numeric criteria ({desc})"
        + (f"; {need} required" if need else "")
    )
    item.missing.append(
        "A person must judge whether the candidate projects are similar in scope; similarity is not decided automatically"
    )
    return _result(ctx, _UNKNOWN, "experience", items=[item],
                   extra_notes=["Past-project similarity is a human judgement; the status stays Unknown."])


# --------------------------------------------------------------------------- fallback
_FALLBACK_MISSING = {
    _CAT.CERTIFICATION: "Evidence of the required certification (certificate, issuing body, expiry date) confirmed by a person",
    _CAT.FINANCIAL: "A machine-readable financial threshold and confirmed company figures to compare it with",
    _CAT.ELIGIBILITY: "Evidence that the company meets this eligibility condition, confirmed by a person",
    _CAT.TECHNICAL: "Evidence of the technical capability (equipment, personnel or past-project records) confirmed by a person",
    _CAT.LEGAL_CONTRACTUAL: "Review by a person with legal competence; ProjectIQ does not assess legal compliance",
    _CAT.SCHEDULE: "Confirmation of the delivery schedule against company capacity and existing commitments",
    _CAT.DELIVERABLE: "Confirmation that the company will deliver this item; the company profile cannot evidence it",
    _CAT.DOCUMENTATION: "The document or declaration required for submission",
    _CAT.EVALUATION: "This looks like an evaluation criterion rather than a condition to satisfy; a person should confirm and may mark it Not applicable",
    _CAT.OTHER: "A person must compare this requirement with company evidence; no automated rule applies",
}


def _fallback(ctx: _Ctx, reason: str) -> MatchResult:
    missing = _FALLBACK_MISSING.get(ctx.category, _FALLBACK_MISSING[_CAT.OTHER])
    return _result(ctx, _UNKNOWN, "no_rule", extra_missing=[missing], extra_notes=[reason])


# ------------------------------------------------------------------------- public API
_RULES = (_rule_financial, _rule_certification, _rule_capability, _rule_experience)


def match_requirement(requirement: Any, company: Any, *, as_of: Any) -> MatchResult:
    """Match one requirement against the company profile. ``as_of`` is a date (or datetime)."""
    as_of_date = _to_date(as_of)
    if as_of_date is None:
        raise ValueError("as_of must be a date or datetime")
    category_value = _value(_get(requirement, "category")) or _CAT.OTHER.value
    try:
        category = RequirementCategory(category_value)
    except ValueError:
        category = _CAT.OTHER
    text = _clean(_get(requirement, "description"))
    ctx = _Ctx(requirement, text, _tokens(text), category, company, as_of_date, _to_date(_get(requirement, "deadline")))

    if _value(_get(requirement, "match_status")) == _NOT_APPLICABLE.value:
        return MatchResult(
            _get(requirement, "id"), str(_get(requirement, "code") or ""), _NOT_APPLICABLE, "manual_not_applicable",
            evidence_summary=_get(requirement, "evidence_summary"),
            notes=("Not applicable is a person's decision; the matcher keeps it.",),
        )
    if not text.strip():
        return _fallback(ctx, "The requirement text is empty.")
    if company is None:
        return _fallback(ctx, "No company profile is linked, so there is no evidence to compare.")
    for rule in _RULES:
        result = rule(ctx)
        if result is not None:
            return result
    return _fallback(ctx, "No structured rule applies; related words alone never change the status.")


def match_requirements(requirements: Iterable[Any], company: Any, *, as_of: Any) -> list[MatchResult]:
    """Match every non-rejected requirement, in input order. Rejected ones are skipped."""
    return [
        match_requirement(r, company, as_of=as_of)
        for r in requirements
        if _vstatus(r) != _REJECTED
    ]


def apply_match_result(requirement: Any, result: MatchResult, *, preserve_reviewed: bool = True) -> bool:
    """Write ``result`` onto a ``Requirement`` row. Returns True when it was written.

    Never overwrites a human decision: a stored ``Not applicable`` is kept, and (with
    ``preserve_reviewed``) so is a non-Unknown status on a requirement a person has marked
    ``Verified``. Pass ``preserve_reviewed=False`` for an explicit "Re-check Fit". The caller
    owns the transaction (commit or roll back).
    """
    current = _value(_get(requirement, "match_status"))
    if current == _NOT_APPLICABLE.value:
        return False
    if preserve_reviewed and _vstatus(requirement) == _VERIFIED and current not in (None, _UNKNOWN.value):
        return False
    requirement.match_status = result.status
    requirement.evidence_summary = result.evidence_summary
    requirement.missing_evidence = result.missing_evidence
    return True