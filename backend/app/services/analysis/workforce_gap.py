"""Workforce gap analysis: required project roles against available company capacity (FR-17).

Compares the project's personnel requirements (``ProjectResource`` rows with
``resource_type == "personnel"``) with the company's role-level capacity
(``CompanyWorkforceRole``). Like ``services/finance`` this module is made of *pure functions*:
no database access, no clock, no randomness and no language model, so the same inputs always
give the same outputs. Inputs are duck-typed (SQLAlchemy objects or plain mappings).

Role-level only: no individual employee is assessed, and nothing here is an employment decision.

Rules
-----
1. **Employed does not mean available.** ``headcount`` is shown as context but is never used as
   capacity. Capacity comes from, in order: the resource's own ``available_quantity`` (a figure
   a person entered for this project), else the linked company role's ``available_headcount``.
   If neither is recorded the availability is **Unknown** and no gap is computed: unknown is
   never treated as zero (which would invent a shortfall) or as ``headcount`` (which would
   invent capacity).
2. **Linking.** A resource is tied to a company role by ``company_workforce_role_id``; otherwise
   by an exact (case-insensitive, whitespace-normalised) role-name match, but only when exactly
   one company role has that name. A name that exists in several departments is *ambiguous* and
   is not guessed; the resource must be linked to a specific role.
3. **Conflicting figures are not resolved silently.** The resource's ``available_quantity``
   conflicts with the company profile when it exceeds the linked role's ``available_headcount``
   or ``headcount``. The row is reported ``Conflicting`` with both figures, and no shortfall is
   computed for it.
4. **Shared capacity.** Resources drawing on the same company role compete for the same people.
   For each role with two or more resources the *peak concurrent demand* over the resources'
   periods is compared with the role's ``available_headcount``; a resource with no or an open
   period is assumed to overlap with everything (flagged ``assumed_concurrent``) so the check
   errs towards showing a clash, not hiding one.
5. **Verification.** Figures that are not ``Verified`` are still analysed (this is planning
   analysis, not a compliance claim) but the row is flagged ``basis_unverified`` so nobody
   mistakes a provisional gap for a confirmed one. ``Rejected`` records are ignored.
6. **Limits, stated plainly.** The data model holds no project-side skill requirements and no
   other-project commitments, so skills and outside commitments are not assessed; role skills
   from the company profile are shown as context only. No costs are computed (cost arithmetic
   belongs to the finance engine). The suggested options (hire, train, subcontract) are options
   to evaluate, not recommendations.
"""
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Optional

from app.models.enums import VerificationStatus
from app.models.resource import ResourceType

WORKFORCE_GAP_VERSION = "workforce-gap-1.0.0"

_VERIFIED = VerificationStatus.VERIFIED.value
_REJECTED = VerificationStatus.REJECTED.value
_CONFLICTING = VerificationStatus.CONFLICTING.value
_REVIEW = VerificationStatus.REQUIRES_REVIEW.value

SUGGESTED_OPTIONS = (
    "Hire additional staff",
    "Train existing staff",
    "Use a subcontractor or agency",
    "Re-plan or phase the work",
)


class RoleCoverage(str, Enum):
    COVERED = "Covered"
    SHORTFALL = "Shortfall"
    UNKNOWN = "Unknown availability"
    CONFLICTING = "Conflicting"
    NOT_REQUIRED = "Not required"


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


def _norm(name: Any) -> str:
    return " ".join(str(name or "").lower().split())


def _code_key(text: str) -> tuple:
    """Natural-sort key ("REQ-2" < "REQ-10"). Parts are tagged so digits and text never compare."""
    return tuple(
        (0, int(p), "") if p.isdigit() else (1, 0, p.lower())
        for p in re.split(r"(\d+)", str(text or ""))
        if p
    )


def _int_or_none(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


# ---------------------------------------------------------------------------- results
@dataclass(frozen=True)
class RoleGap:
    """Coverage of one personnel resource."""

    resource_id: Optional[int]
    role: str
    company_role_id: Optional[int]
    company_role_name: Optional[str]
    required: int
    available: Optional[int]  # None = unknown (never zero by default)
    availability_source: Optional[str]  # "project_resource" | "company_role" | None
    employed_headcount: Optional[int]  # context only, never capacity
    coverage: RoleCoverage
    shortfall: Optional[int]  # None unless coverage is Shortfall or Covered
    surplus: Optional[int]
    candidate_available: tuple[int, ...]  # the competing figures when Conflicting
    required_from: Optional[date]
    required_to: Optional[date]
    company_role_skills: tuple[str, ...]  # context only
    flags: tuple[str, ...]
    notes: tuple[str, ...]
    missing_information: tuple[str, ...]
    suggested_options: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "role": self.role,
            "company_role_id": self.company_role_id,
            "company_role_name": self.company_role_name,
            "required": self.required,
            "available": self.available,
            "availability_source": self.availability_source,
            "employed_headcount": self.employed_headcount,
            "coverage": self.coverage.value,
            "shortfall": self.shortfall,
            "surplus": self.surplus,
            "candidate_available": list(self.candidate_available),
            "required_from": self.required_from.isoformat() if self.required_from else None,
            "required_to": self.required_to.isoformat() if self.required_to else None,
            "company_role_skills": list(self.company_role_skills),
            "flags": list(self.flags),
            "notes": list(self.notes),
            "missing_information": list(self.missing_information),
            "suggested_options": list(self.suggested_options),
        }


@dataclass(frozen=True)
class SharedCapacityFinding:
    """Resources drawing on the same company role whose combined peak demand is too high."""

    company_role_id: int
    company_role_name: str
    resource_ids: tuple[Optional[int], ...]
    peak_demand: int
    available: Optional[int]
    peak_on: Optional[date]  # None = at the start of the earliest open period
    assumed_concurrent: bool
    overcommitted: bool
    shortfall: Optional[int]
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_role_id": self.company_role_id,
            "company_role_name": self.company_role_name,
            "resource_ids": list(self.resource_ids),
            "peak_demand": self.peak_demand,
            "available": self.available,
            "peak_on": self.peak_on.isoformat() if self.peak_on else None,
            "assumed_concurrent": self.assumed_concurrent,
            "overcommitted": self.overcommitted,
            "shortfall": self.shortfall,
            "note": self.note,
        }


@dataclass(frozen=True)
class WorkforceGapReport:
    roles: tuple[RoleGap, ...]
    shared_capacity: tuple[SharedCapacityFinding, ...]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "roles": [r.to_dict() for r in self.roles],
            "shared_capacity": [s.to_dict() for s in self.shared_capacity],
            "summary": self.summary,
        }


# ------------------------------------------------------------------------- analysis
def _resolve_company_role(resource: Any, roles: list[Any]) -> tuple[Optional[Any], Optional[str]]:
    """(role, note). Linked id first, then a unique exact name match; ambiguity is reported."""
    link = _get(resource, "company_workforce_role_id")
    if link is not None:
        for role in roles:
            if _get(role, "id") == link:
                return role, None
        return None, "The linked company role was not found among the company's roles (or was rejected)."
    name = _norm(_get(resource, "name"))
    matches = [r for r in roles if _norm(_get(r, "role")) == name] if name else []
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        departments = sorted({str(_get(r, "department") or "no department") for r in matches})
        return None, (
            f"The role name matches {len(matches)} company roles ({', '.join(departments)}); "
            "link the resource to a specific role."
        )
    return None, None


def _analyse_resource(resource: Any, roles: list[Any]) -> RoleGap:
    required = _int_or_none(_get(resource, "required_quantity")) or 0
    explicit = _int_or_none(_get(resource, "available_quantity"))
    role, link_note = _resolve_company_role(resource, roles)
    role_available = _int_or_none(_get(role, "available_headcount")) if role is not None else None
    role_headcount = _int_or_none(_get(role, "headcount")) if role is not None else None

    flags: list[str] = []
    notes: list[str] = [link_note] if link_note else []
    missing: list[str] = []
    candidates: tuple[int, ...] = ()

    if role is None:
        flags.append("no_company_role")
        if not link_note:
            notes.append("No company role with this name is recorded; availability cannot be taken from the profile.")
    if role is not None and _vstatus(role) != _VERIFIED:
        flags.append("basis_unverified")
    if _vstatus(resource) != _VERIFIED and explicit is not None:
        flags.append("basis_unverified")
    if role is not None and _vstatus(role) == _CONFLICTING:
        flags.append("conflicting_record")

    conflict = False
    if explicit is not None and role is not None:
        if role_available is not None and explicit > role_available:
            conflict, candidates = True, (explicit, role_available)
            notes.append(
                f"The resource claims {explicit} available but the company profile shows only "
                f"{role_available} available."
            )
        elif role_headcount is not None and explicit > role_headcount:
            conflict, candidates = True, (explicit, role_headcount)
            notes.append(
                f"The resource claims {explicit} available but the company employs only {role_headcount} in this role."
            )
    if "conflicting_record" in flags:
        conflict = True
        notes.append("The company role record is marked Conflicting; its figures are not used until resolved.")

    available: Optional[int]
    source: Optional[str]
    if conflict:
        available, source = None, None
        flags.append("conflicting_figures")
        missing.append("A person must resolve which availability figure is correct")
    elif explicit is not None:
        available, source = explicit, "project_resource"
    elif role_available is not None:
        available, source = role_available, "company_role"
    else:
        available, source = None, None
        if role is not None:
            notes.append("Employed headcount is not availability; availability is not recorded for this role.")
        missing.append("Available headcount for this role (employed does not mean available)")

    if required == 0:
        coverage = RoleCoverage.NOT_REQUIRED
        shortfall, surplus = 0, None
    elif conflict:
        coverage, shortfall, surplus = RoleCoverage.CONFLICTING, None, None
    elif available is None:
        coverage, shortfall, surplus = RoleCoverage.UNKNOWN, None, None
    elif available >= required:
        coverage, shortfall, surplus = RoleCoverage.COVERED, 0, available - required
    else:
        coverage, shortfall, surplus = RoleCoverage.SHORTFALL, required - available, None

    skills = _get(role, "skills") if role is not None else None
    return RoleGap(
        resource_id=_get(resource, "id"),
        role=str(_get(resource, "name") or ""),
        company_role_id=_get(role, "id") if role is not None else None,
        company_role_name=_get(role, "role") if role is not None else None,
        required=required,
        available=available,
        availability_source=source,
        employed_headcount=role_headcount,
        coverage=coverage,
        shortfall=shortfall,
        surplus=surplus,
        candidate_available=candidates,
        required_from=_get(resource, "required_from"),
        required_to=_get(resource, "required_to"),
        company_role_skills=tuple(str(s) for s in skills) if isinstance(skills, (list, tuple)) else (),
        flags=tuple(dict.fromkeys(flags)),
        notes=tuple(dict.fromkeys(notes)),
        missing_information=tuple(missing),
        suggested_options=SUGGESTED_OPTIONS if coverage is RoleCoverage.SHORTFALL else (),
    )


def _peak_demand(rows: list[tuple[Any, int]]) -> tuple[int, Optional[date], bool]:
    """Peak concurrent demand over the rows' periods: (peak, date of peak, assumed_concurrent)."""
    assumed = any(_get(r, "required_from") is None or _get(r, "required_to") is None for r, _ in rows)
    starts = {_get(r, "required_from") for r, _ in rows if _get(r, "required_from") is not None}
    open_start = any(_get(r, "required_from") is None for r, _ in rows)
    candidates: list[Optional[date]] = sorted(starts)
    if open_start or not candidates:
        candidates.insert(0, None)  # the beginning of time: open-start rows are active here
    best, best_day = -1, None
    for day in candidates:
        total = 0
        for r, qty in rows:
            start, end = _get(r, "required_from"), _get(r, "required_to")
            if day is None:
                active = start is None  # the open beginning: only open-start rows are active
            else:
                active = (start is None or start <= day) and (end is None or end >= day)
            if active:
                total += qty
        if total > best:
            best, best_day = total, day
    return best, best_day, assumed


def _shared_capacity(resources: list[Any], roles: list[Any], gaps: list[RoleGap]) -> list[SharedCapacityFinding]:
    by_role: dict[int, list[tuple[Any, int]]] = defaultdict(list)
    for resource, gap in zip(resources, gaps):
        if gap.company_role_id is not None and gap.required > 0:
            by_role[gap.company_role_id].append((resource, gap.required))
    findings = []
    role_index = {_get(r, "id"): r for r in roles}
    for role_id in sorted(by_role):
        rows = by_role[role_id]
        if len(rows) < 2:
            continue
        role = role_index[role_id]
        available = _int_or_none(_get(role, "available_headcount"))
        peak, day, assumed = _peak_demand(rows)
        over = available is not None and peak > available
        if available is None:
            note = (
                f"Combined peak demand is {peak}, but availability of '{_get(role, 'role')}' is unknown, "
                "so no clash can be confirmed or ruled out."
            )
        elif over:
            note = (
                f"Combined peak demand of {peak} exceeds the {available} available in '{_get(role, 'role')}', "
                "even if each resource fits on its own."
            )
        else:
            note = f"Combined peak demand of {peak} fits within the {available} available."
        if assumed:
            note += " Some periods are missing or open, so the resources are assumed to overlap."
        findings.append(
            SharedCapacityFinding(
                company_role_id=role_id,
                company_role_name=str(_get(role, "role") or ""),
                resource_ids=tuple(_get(r, "id") for r, _ in rows),
                peak_demand=peak,
                available=available,
                peak_on=day,
                assumed_concurrent=assumed,
                overcommitted=over,
                shortfall=(peak - available) if over else None,
                note=note,
            )
        )
    return findings


def analyse_workforce(resources: Iterable[Any], company_roles: Iterable[Any]) -> WorkforceGapReport:
    """Compare personnel requirements with company role capacity.

    ``resources`` may contain every project resource; only personnel rows are analysed.
    Rejected resources and rejected company roles are ignored.
    """
    roles = [r for r in company_roles if _vstatus(r) != _REJECTED]
    personnel = [
        r
        for r in resources
        if _value(_get(r, "resource_type")) == ResourceType.PERSONNEL.value and _vstatus(r) != _REJECTED
    ]
    personnel.sort(key=lambda r: (_code_key(str(_get(r, "name") or "")), _get(r, "id") or 0))
    gaps = [_analyse_resource(r, roles) for r in personnel]
    shared = _shared_capacity(personnel, roles, gaps)

    counts = {c.value: 0 for c in RoleCoverage}
    for g in gaps:
        counts[g.coverage.value] += 1
    known = [g for g in gaps if g.coverage in (RoleCoverage.COVERED, RoleCoverage.SHORTFALL)]
    lower_bound = any(g.coverage in (RoleCoverage.UNKNOWN, RoleCoverage.CONFLICTING) for g in gaps)
    summary = {
        "personnel_resources": len(gaps),
        "by_coverage": counts,
        "known_shortfall_total": sum(g.shortfall or 0 for g in known),
        "shortfall_is_lower_bound": lower_bound,
        "roles_with_unknown_availability": [g.role for g in gaps if g.coverage is RoleCoverage.UNKNOWN],
        "roles_with_conflicts": [g.role for g in gaps if g.coverage is RoleCoverage.CONFLICTING],
        "shared_capacity_overcommitted": [s.company_role_name for s in shared if s.overcommitted],
        "unverified_basis": [g.role for g in gaps if "basis_unverified" in g.flags],
        "basis": (
            "Required quantity against available (not employed) headcount. Unknown availability is not "
            "counted as a shortfall or as capacity; the shortfall total is a lower bound while any role is "
            "Unknown or Conflicting. Skills and commitments outside this project are not assessed."
        ),
        "version": WORKFORCE_GAP_VERSION,
    }
    return WorkforceGapReport(tuple(gaps), tuple(shared), summary)