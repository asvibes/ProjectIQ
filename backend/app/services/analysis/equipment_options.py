"""Equipment options: required project equipment against company equipment (FR-17).

Compares the project's equipment needs (``ProjectResource`` rows with
``resource_type == "equipment"``) with the company's equipment register (``CompanyEquipment``)
and, where shown, with the tender requirements that rely on that equipment. Like
``services/finance`` and ``analysis/workforce_gap`` this module is made of *pure functions*: no
database access, no clock, no randomness and no language model, so the same inputs always
give the same outputs. Inputs are duck-typed (SQLAlchemy objects or plain mappings).

Rules
-----
1. **Unknown is never zero.** Units available for the project come from, in order: the
   resource's own ``available_quantity`` (a figure a person entered for this project), else the
   linked company item's ``quantity`` *when its ownership is recorded as owned or leased*. A
   record with ``unknown`` ownership does not establish that the company controls the units, so
   its quantity is shown but not used as capacity (a recorded quantity of 0 is a real zero).
   If neither source gives a figure the row is **Unknown availability** and no gap is computed.
2. **Linking.** A resource is tied to a company item by ``company_equipment_id``; otherwise by an
   exact (case-insensitive, whitespace-normalised) match on the item's ``name`` or
   ``equipment_type``, but only when exactly one item matches. Several matches are *ambiguous*
   and not guessed or summed (they may be duplicates); the resource must be linked.
3. **Conflicting figures are not resolved silently.** A resource's ``available_quantity`` above
   the linked item's recorded ``quantity``, or a company item marked ``Conflicting``, makes the
   row ``Conflicting`` with both figures shown and no shortfall computed.
4. **Shared capacity.** Resources drawing on the same company item compete for the same units.
   For an item with two or more resources the *peak concurrent demand* over their periods is
   compared with the item's usable quantity (rule 1); a resource with an open or missing period
   is assumed to overlap with everything (``assumed_concurrent``) so a clash is shown, not hidden.
5. **Verification.** Figures that are not ``Verified`` are still analysed (this is planning
   analysis, not a compliance claim) but the row carries ``basis_unverified``. ``Rejected``
   records are ignored. Leased units count as capacity but are flagged ``leased_capacity``: the
   data model records no lease term, so whether a lease covers the project period is unknown.
6. **Tender requirements.** Pass the matcher's ``MatchResult`` list as ``match_results``. A
   requirement is linked to a resource when its evidence cites that resource's company item; each
   link carries the requirement's match status as the matcher produced it and is never
   re-derived here. Requirements whose evidence cites company equipment that no project resource
   draws on are listed separately as ``unlinked_requirements`` (an observation for a person: the
   plan may omit equipment the tender asks about). Nothing is inferred when ``match_results`` is
   omitted, and requirements marked Not applicable are skipped.
7. **Limits, stated plainly.** Equipment *capacity against a specification* (for example
   "50 t") is evaluated by the requirement matcher, not here; the recorded capacity text is shown
   as context. Commitments to other projects, lease terms and equipment condition are not
   modelled and not assessed. No costs are computed (cost arithmetic belongs to the finance
   engine): ``unit_cost``, ``unit`` and ``currency`` are shown as recorded, and an unknown cost
   is reported as missing information. The suggested options (purchase, rent or lease,
   subcontract, re-plan) are options to evaluate, never recommendations, and are only offered
   for a confirmed shortfall.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Optional

from app.models.enums import EquipmentOwnership, MatchStatus, VerificationStatus
from app.models.resource import ResourceType

EQUIPMENT_OPTIONS_VERSION = "equipment-options-1.0.0"

_VERIFIED = VerificationStatus.VERIFIED.value
_REJECTED = VerificationStatus.REJECTED.value
_CONFLICTING = VerificationStatus.CONFLICTING.value
_REVIEW = VerificationStatus.REQUIRES_REVIEW.value
_OWNED = EquipmentOwnership.OWNED.value
_LEASED = EquipmentOwnership.LEASED.value
_NOT_APPLICABLE = MatchStatus.NOT_APPLICABLE.value

SUGGESTED_OPTIONS = (
    "Purchase additional units",
    "Rent or lease additional units",
    "Subcontract the work that needs this equipment",
    "Re-plan or phase the work",
)


class EquipmentCoverage(str, Enum):
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


def _int_or_none(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _money(value: Any) -> Optional[Decimal]:
    """A recorded, finite, non-negative amount, or ``None`` (unknown). Never defaults to zero."""
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return amount if amount.is_finite() and amount >= 0 else None


def _clip(text: Any, limit: int = 120) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


# ---------------------------------------------------------------------------- results
@dataclass(frozen=True)
class RequirementLink:
    """A tender requirement whose match evidence cites a company equipment item."""

    requirement_code: str
    requirement_id: Optional[int]
    match_status: str  # as produced by the matcher
    needs_verification: bool
    conflict: bool
    equipment_id: Optional[int]
    equipment_label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_code": self.requirement_code,
            "requirement_id": self.requirement_id,
            "match_status": self.match_status,
            "needs_verification": self.needs_verification,
            "conflict": self.conflict,
            "equipment_id": self.equipment_id,
            "equipment_label": self.equipment_label,
        }


@dataclass(frozen=True)
class EquipmentAssessment:
    """Coverage of one equipment resource."""

    resource_id: Optional[int]
    name: str
    company_equipment_id: Optional[int]
    company_equipment_name: Optional[str]
    equipment_type: Optional[str]
    ownership: Optional[str]  # "owned" | "leased" | "unknown" | None when no item is linked
    recorded_quantity: Optional[int]  # the register figure, context unless used as capacity
    recorded_capacity: Optional[str]  # context only; not compared with any specification here
    required: int
    available: Optional[int]  # None = unknown (never zero by default)
    availability_source: Optional[str]  # "project_resource" | "company_equipment" | None
    coverage: EquipmentCoverage
    shortfall: Optional[int]
    surplus: Optional[int]
    candidate_available: tuple[int, ...]  # the competing figures when Conflicting
    required_from: Optional[date]
    required_to: Optional[date]
    unit: Optional[str]
    unit_cost: Optional[Decimal]  # as recorded; None = unknown
    currency: Optional[str]
    requirements: tuple[RequirementLink, ...]
    flags: tuple[str, ...]
    notes: tuple[str, ...]
    missing_information: tuple[str, ...]
    suggested_options: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "name": self.name,
            "company_equipment_id": self.company_equipment_id,
            "company_equipment_name": self.company_equipment_name,
            "equipment_type": self.equipment_type,
            "ownership": self.ownership,
            "recorded_quantity": self.recorded_quantity,
            "recorded_capacity": self.recorded_capacity,
            "required": self.required,
            "available": self.available,
            "availability_source": self.availability_source,
            "coverage": self.coverage.value,
            "shortfall": self.shortfall,
            "surplus": self.surplus,
            "candidate_available": list(self.candidate_available),
            "required_from": self.required_from.isoformat() if self.required_from else None,
            "required_to": self.required_to.isoformat() if self.required_to else None,
            "unit": self.unit,
            "unit_cost": str(self.unit_cost) if self.unit_cost is not None else None,
            "currency": self.currency,
            "requirements": [r.to_dict() for r in self.requirements],
            "flags": list(self.flags),
            "notes": list(self.notes),
            "missing_information": list(self.missing_information),
            "suggested_options": list(self.suggested_options),
        }


@dataclass(frozen=True)
class SharedEquipmentFinding:
    """Resources drawing on the same company item whose combined peak demand is too high."""

    company_equipment_id: int
    company_equipment_name: str
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
            "company_equipment_id": self.company_equipment_id,
            "company_equipment_name": self.company_equipment_name,
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
class EquipmentOptionsReport:
    items: tuple[EquipmentAssessment, ...]
    shared_capacity: tuple[SharedEquipmentFinding, ...]
    unlinked_requirements: tuple[RequirementLink, ...]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [i.to_dict() for i in self.items],
            "shared_capacity": [s.to_dict() for s in self.shared_capacity],
            "unlinked_requirements": [r.to_dict() for r in self.unlinked_requirements],
            "summary": self.summary,
        }


# ------------------------------------------------------------------------- analysis
def _resolve_item(resource: Any, items: list[Any]) -> tuple[Optional[Any], Optional[str], bool]:
    """(item, note, ambiguous). Linked id first, then a unique exact name/type match; ambiguity
    is reported, never guessed."""
    link = _get(resource, "company_equipment_id")
    if link is not None:
        for item in items:
            if _get(item, "id") == link:
                return item, None, False
        return None, "The linked company equipment record was not found among the company's equipment (or was rejected).", False
    name = _norm(_get(resource, "name"))
    matches = [i for i in items if name and name in (_norm(_get(i, "name")), _norm(_get(i, "equipment_type")))]
    if len(matches) == 1:
        return matches[0], None, False
    if len(matches) > 1:
        shown = ", ".join(sorted(f"'{_clip(_get(m, 'name'), 60)}' ({_value(_get(m, 'ownership')) or 'unknown'})" for m in matches))
        return None, f"The name matches {len(matches)} company equipment records ({shown}); link the resource to a specific record.", True
    return None, None, False


def _usable_quantity(item: Any) -> tuple[Optional[int], Optional[str]]:
    """(quantity the company can be taken to control, ownership). Quantity of units whose
    ownership is not recorded is not usable; a recorded 0 is a real zero."""
    quantity = _int_or_none(_get(item, "quantity"))
    ownership = str(_value(_get(item, "ownership")) or EquipmentOwnership.UNKNOWN.value)
    if quantity is None:
        return None, ownership
    if quantity == 0 or ownership in (_OWNED, _LEASED):
        return quantity, ownership
    return None, ownership


def _links_for(item_id: Optional[int], match_results: list[Any]) -> tuple[RequirementLink, ...]:
    if item_id is None:
        return ()
    return tuple(_requirement_links(match_results, only=item_id))


def _requirement_links(match_results: list[Any], *, only: Optional[int] = None, exclude: frozenset = frozenset()) -> list[RequirementLink]:
    links: dict[tuple[str, Optional[int]], RequirementLink] = {}
    for result in match_results:
        if _value(_get(result, "status")) == _NOT_APPLICABLE:
            continue
        for evidence in _get(result, "evidence") or ():
            if _get(evidence, "kind") != "equipment":
                continue
            record_id = _get(evidence, "record_id")
            if (only is not None and record_id != only) or record_id in exclude:
                continue
            code = str(_get(result, "requirement_code") or "")
            links.setdefault(
                (code, record_id),
                RequirementLink(
                    requirement_code=code,
                    requirement_id=_get(result, "requirement_id"),
                    match_status=str(_value(_get(result, "status")) or MatchStatus.UNKNOWN.value),
                    needs_verification=bool(_get(result, "needs_verification", False)),
                    conflict=bool(_get(result, "conflict", False)),
                    equipment_id=record_id,
                    equipment_label=_clip(_get(evidence, "label")),
                ),
            )
    return sorted(links.values(), key=lambda link: (link.requirement_code.lower(), link.equipment_id or 0))


def _assess(resource: Any, items: list[Any], match_results: list[Any]) -> EquipmentAssessment:
    required = _int_or_none(_get(resource, "required_quantity")) or 0
    explicit = _int_or_none(_get(resource, "available_quantity"))
    item, link_note, ambiguous = _resolve_item(resource, items)
    recorded = _int_or_none(_get(item, "quantity")) if item is not None else None
    usable, ownership = _usable_quantity(item) if item is not None else (None, None)

    flags: list[str] = []
    notes: list[str] = [link_note] if link_note else []
    missing: list[str] = []
    candidates: tuple[int, ...] = ()

    if item is None:
        flags.append("no_company_equipment")
        if ambiguous:
            flags.append("ambiguous_company_match")
        elif not link_note:
            notes.append("No company equipment with this name or type is recorded; availability cannot be taken from the register.")
    else:
        if _vstatus(item) != _VERIFIED:
            flags.append("basis_unverified")
        if _vstatus(item) == _CONFLICTING:
            flags.append("conflicting_record")
        if ownership == EquipmentOwnership.UNKNOWN.value:
            flags.append("ownership_unknown")
    if _vstatus(resource) != _VERIFIED and explicit is not None:
        flags.append("basis_unverified")

    conflict = False
    if explicit is not None and item is not None and recorded is not None and explicit > recorded:
        conflict, candidates = True, (explicit, recorded)
        notes.append(f"The resource claims {explicit} available but the company equipment register records only {recorded}.")
    if "conflicting_record" in flags:
        conflict = True
        notes.append("The company equipment record is marked Conflicting; its figures are not used until resolved.")

    available: Optional[int]
    source: Optional[str]
    if conflict:
        available, source = None, None
        flags.append("conflicting_figures")
        missing.append("A person must resolve which quantity is correct")
    elif explicit is not None:
        available, source = explicit, "project_resource"
    elif usable is not None:
        available, source = usable, "company_equipment"
        if usable > 0:
            flags.append("register_quantity_used")
            notes.append("Capacity is the register quantity; commitments to other projects are not recorded.")
    else:
        available, source = None, None
        if item is not None and recorded is not None and ownership == EquipmentOwnership.UNKNOWN.value:
            notes.append(f"The register records {recorded} but not whether they are owned or leased, so it is not counted as capacity.")
            missing.append(f"Ownership (owned or leased) of '{_clip(_get(item, 'name'), 60)}'")
        missing.append("Number of units available for this project")

    if available is not None and item is not None and ownership == _LEASED and available > 0:
        flags.append("leased_capacity")
        notes.append("Capacity is leased; the data model records no lease term, so cover for the project period is unconfirmed.")

    if required == 0:
        coverage, shortfall, surplus = EquipmentCoverage.NOT_REQUIRED, 0, None
    elif conflict:
        coverage, shortfall, surplus = EquipmentCoverage.CONFLICTING, None, None
    elif available is None:
        coverage, shortfall, surplus = EquipmentCoverage.UNKNOWN, None, None
    elif available >= required:
        coverage, shortfall, surplus = EquipmentCoverage.COVERED, 0, available - required
    else:
        coverage, shortfall, surplus = EquipmentCoverage.SHORTFALL, required - available, None

    unit_cost = _money(_get(resource, "unit_cost"))
    if coverage is EquipmentCoverage.SHORTFALL:
        if unit_cost is None:
            missing.append("Unit cost for this equipment (needed to compare the options)")
        if _get(resource, "required_from") is None or _get(resource, "required_to") is None:
            missing.append("Required period (needed to size rental, lease or subcontract options)")

    capacity = _get(item, "capacity") if item is not None else None
    item_id = _get(item, "id") if item is not None else None
    return EquipmentAssessment(
        resource_id=_get(resource, "id"),
        name=str(_get(resource, "name") or ""),
        company_equipment_id=item_id,
        company_equipment_name=_get(item, "name") if item is not None else None,
        equipment_type=_get(item, "equipment_type") if item is not None else None,
        ownership=ownership,
        recorded_quantity=recorded,
        recorded_capacity=str(capacity) if capacity else None,
        required=required,
        available=available,
        availability_source=source,
        coverage=coverage,
        shortfall=shortfall,
        surplus=surplus,
        candidate_available=candidates,
        required_from=_get(resource, "required_from"),
        required_to=_get(resource, "required_to"),
        unit=_get(resource, "unit"),
        unit_cost=unit_cost,
        currency=_get(resource, "currency"),
        requirements=_links_for(item_id, match_results),
        flags=tuple(dict.fromkeys(flags)),
        notes=tuple(dict.fromkeys(notes)),
        missing_information=tuple(dict.fromkeys(missing)),
        suggested_options=SUGGESTED_OPTIONS if coverage is EquipmentCoverage.SHORTFALL else (),
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
                active = start is None
            else:
                active = (start is None or start <= day) and (end is None or end >= day)
            if active:
                total += qty
        if total > best:
            best, best_day = total, day
    return best, best_day, assumed


def _shared_capacity(resources: list[Any], items: list[Any], assessments: list[EquipmentAssessment]) -> list[SharedEquipmentFinding]:
    by_item: dict[int, list[tuple[Any, int]]] = defaultdict(list)
    for resource, a in zip(resources, assessments):
        if a.company_equipment_id is not None and a.required > 0:
            by_item[a.company_equipment_id].append((resource, a.required))
    index = {_get(i, "id"): i for i in items}
    findings = []
    for item_id in sorted(by_item):
        rows = by_item[item_id]
        if len(rows) < 2:
            continue
        item = index[item_id]
        name = str(_get(item, "name") or "")
        available = None if _vstatus(item) == _CONFLICTING else _usable_quantity(item)[0]
        peak, day, assumed = _peak_demand(rows)
        over = available is not None and peak > available
        if available is None:
            note = f"Combined peak demand is {peak}, but the usable quantity of '{name}' is unknown, so no clash can be confirmed or ruled out."
        elif over:
            note = f"Combined peak demand of {peak} exceeds the {available} usable of '{name}', even if each resource fits on its own."
        else:
            note = f"Combined peak demand of {peak} fits within the {available} usable."
        if assumed:
            note += " Some periods are missing or open, so the resources are assumed to overlap."
        findings.append(SharedEquipmentFinding(
            company_equipment_id=item_id, company_equipment_name=name,
            resource_ids=tuple(_get(r, "id") for r, _ in rows), peak_demand=peak, available=available,
            peak_on=day, assumed_concurrent=assumed, overcommitted=over,
            shortfall=(peak - available) if over else None, note=note,
        ))
    return findings


def analyse_equipment(
    resources: Iterable[Any],
    company_equipment: Iterable[Any],
    match_results: Optional[Iterable[Any]] = None,
) -> EquipmentOptionsReport:
    """Compare equipment requirements with the company's equipment register.

    ``resources`` may contain every project resource; only equipment rows are analysed.
    Rejected resources and rejected company equipment are ignored. ``match_results`` is the
    optional ``requirement_matcher`` output used to link tender requirements (rule 6).
    """
    items = [i for i in company_equipment if _vstatus(i) != _REJECTED]
    results = list(match_results or ())
    equipment = [
        r for r in resources
        if _value(_get(r, "resource_type")) == ResourceType.EQUIPMENT.value and _vstatus(r) != _REJECTED
    ]
    equipment.sort(key=lambda r: (_norm(_get(r, "name")), _get(r, "id") or 0))
    assessments = [_assess(r, items, results) for r in equipment]
    shared = _shared_capacity(equipment, items, assessments)
    used_items = frozenset(a.company_equipment_id for a in assessments if a.company_equipment_id is not None)
    unlinked = _requirement_links(results, exclude=used_items)

    counts = {c.value: 0 for c in EquipmentCoverage}
    for a in assessments:
        counts[a.coverage.value] += 1
    known = [a for a in assessments if a.coverage in (EquipmentCoverage.COVERED, EquipmentCoverage.SHORTFALL)]
    lower_bound = any(a.coverage in (EquipmentCoverage.UNKNOWN, EquipmentCoverage.CONFLICTING) for a in assessments)
    summary = {
        "equipment_resources": len(assessments),
        "by_coverage": counts,
        "known_shortfall_total": sum(a.shortfall or 0 for a in known),
        "shortfall_is_lower_bound": lower_bound,
        "resources_with_unknown_availability": [a.name for a in assessments if a.coverage is EquipmentCoverage.UNKNOWN],
        "resources_with_conflicts": [a.name for a in assessments if a.coverage is EquipmentCoverage.CONFLICTING],
        "shared_capacity_overcommitted": [s.company_equipment_name for s in shared if s.overcommitted],
        "unverified_basis": [a.name for a in assessments if "basis_unverified" in a.flags],
        "leased_dependent": [a.name for a in assessments if "leased_capacity" in a.flags],
        "unlinked_requirement_codes": sorted({r.requirement_code for r in unlinked}),
        "basis": (
            "Required quantity against the units available for this project: a person-entered figure, else the register "
            "quantity of owned or leased units. Unknown availability is not counted as a shortfall or as capacity; the "
            "shortfall total is a lower bound while any resource is Unknown or Conflicting. Capacity against a "
            "specification, other-project commitments, lease terms and condition are not assessed, and no costs are computed."
        ),
        "version": EQUIPMENT_OPTIONS_VERSION,
    }
    return EquipmentOptionsReport(tuple(assessments), tuple(shared), tuple(unlinked), summary)