"""Cost model: validated inputs, shared Decimal helpers and the cost build-up (FR-21).

Everything in ``services/finance`` is a *pure function*: no database access, no clock, no
randomness, so the same inputs always give the same outputs (NFR "Determinism"). This module
is the base of the dependency chain ``cost_model -> bid_pricing -> breakeven -> cashflow``.

Formulas
--------
For every active cost line (``verification_status != "Rejected"``)::

    line_total   = round_money(quantity * unit_cost)
    direct_cost  = sum(line_total)
    contingency  = round_money(direct_cost * contingency_rate)
    overhead     = round_money((direct_cost + contingency) * overhead_rate)
    total_cost   = direct_cost + contingency + overhead

``site_overhead`` lines are *direct* costs (they sit in ``direct_cost``). ``overhead_rate`` is
head-office overhead charged on top, so nothing is counted twice.

Fixed / variable split (used by break-even). Contingency and overhead are allocated to the
fixed and variable parts pro rata to their direct cost; the variable part is the residual so
``fixed_cost + variable_cost == total_cost`` exactly::

    fixed_contingency = round_money(fixed_direct * contingency_rate)
    fixed_overhead    = round_money((fixed_direct + fixed_contingency) * overhead_rate)
    fixed_cost        = fixed_direct + fixed_contingency + fixed_overhead
    variable_cost     = total_cost - fixed_cost

Rounding rules
--------------
* Money: 2 decimal places, ``ROUND_HALF_UP`` (same as ``app.models.types.Money``).
* Ratios (margins, markups, shares): 4 decimal places, ``ROUND_HALF_UP`` (same as ``Rate``).
* Rounding happens at each *named step above* and sums are of already-rounded parts, so every
  displayed total equals the sum of the displayed components.
* Arithmetic runs in a 60-digit context, so intermediate products cannot overflow or lose
  precision.

Unknown values (NULL) are never treated as zero
-----------------------------------------------
A line with ``unit_cost = None``, a ``contingency_rate`` or ``overhead_rate`` of ``None`` (to
mean "no contingency" the rate must be an explicit ``0``) or an empty cost list make the model
*incomplete*: ``direct_cost`` / ``total_cost`` are ``None`` and the reasons are listed. The
sum of what *is* known is exposed separately as ``known_direct_subtotal`` and must be shown as
"at least".

Limitations
-----------
No tax (VAT/GST), escalation/inflation, financing cost or bond fees: the data model has no
inputs for them. One currency per model; there is no conversion.

Result dictionaries are JSON-safe (Decimals as plain strings such as ``"1250.00"``), so they
can be stored in ``FinancialModel.results`` / ``Scenario.results``.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Context, Decimal, InvalidOperation
from typing import Any, Optional

from app.models.financial_model import CostBehavior, CostCategory

ENGINE_VERSION = "finance-1.0.0"

ZERO = Decimal("0")
ONE = Decimal("1")
CENT = Decimal("0.01")
RATE_STEP = Decimal("0.0001")
MAX_MONTHS = 1200  # 100 years: bounds the cash-flow series so hostile/garbage input cannot exhaust memory

REJECTED = "Rejected"
# Statuses meaning "a person still has to look at this number" (not a reason to exclude it).
NEEDS_REVIEW_STATUSES = frozenset({"Requires review", "Conflicting", "Outdated", "Missing"})

_CTX = Context(prec=60, rounding=ROUND_HALF_UP)


class FinanceInputError(ValueError):
    """Raised for malformed inputs (negative money, rates outside 0..1, bad types)."""


# --------------------------------------------------------------------------- helpers
def mul(a: Decimal, b: Decimal) -> Decimal:
    return _CTX.multiply(a, b)


def div(a: Decimal, b: Decimal) -> Decimal:
    if b == 0:
        raise ZeroDivisionError("division by zero in finance engine")
    return _CTX.divide(a, b)


def round_money(value: Decimal, rounding: str = ROUND_HALF_UP) -> Decimal:
    return value.quantize(CENT, rounding=rounding, context=_CTX)


def round_rate(value: Decimal) -> Decimal:
    return value.quantize(RATE_STEP, rounding=ROUND_HALF_UP, context=_CTX)


def to_decimal(value: Any, name: str) -> Decimal:
    """Convert int/str/float/Decimal to a finite Decimal. Floats go via ``str`` (no binary noise)."""
    if isinstance(value, bool) or value is None:
        raise FinanceInputError(f"{name} is not a valid number: {value!r}")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, str, float)):
        try:
            result = Decimal(str(value).strip())
        except InvalidOperation as exc:
            raise FinanceInputError(f"{name} is not a valid number: {value!r}") from exc
    else:
        raise FinanceInputError(f"{name} is not a valid number: {value!r}")
    if not result.is_finite():
        raise FinanceInputError(f"{name} must be finite")
    return result


def optional_money(value: Any, name: str) -> Optional[Decimal]:
    """``None`` stays ``None`` (unknown). Otherwise a finite, non-negative Decimal."""
    if value is None:
        return None
    amount = to_decimal(value, name)
    if amount < 0:
        raise FinanceInputError(f"{name} cannot be negative")
    return amount


def optional_rate(value: Any, name: str) -> Optional[Decimal]:
    """``None`` stays ``None`` (unknown). Otherwise a fraction between 0 and 1 inclusive."""
    if value is None:
        return None
    rate = to_decimal(value, name)
    if rate < 0 or rate > 1:
        raise FinanceInputError(f"{name} must be a fraction between 0 and 1, got {rate}")
    return rate


def optional_int(value: Any, name: str, minimum: int, maximum: Optional[int] = None) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise FinanceInputError(f"{name} must be a whole number")
    if value < minimum:
        raise FinanceInputError(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise FinanceInputError(f"{name} cannot exceed {maximum}")
    return value


def fmt_money(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else format(round_money(value), "f")


def fmt_rate(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else format(round_rate(value), "f")


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


# ------------------------------------------------------------------------ input types
@dataclass(frozen=True)
class CostLine:
    """One cost line. ``unit_cost=None`` means *unknown*, never zero."""

    id: Optional[int]
    description: str
    category: str
    quantity: Decimal
    unit_cost: Optional[Decimal]
    cost_behavior: Optional[str] = None  # "fixed" | "variable" | None (not classified)
    verification_status: str = "Requires review"
    start_month: Optional[int] = None
    end_month: Optional[int] = None

    def __post_init__(self) -> None:
        quantity = to_decimal(self.quantity, "quantity")
        if quantity < 0:
            raise FinanceInputError("quantity cannot be negative")
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "unit_cost", optional_money(self.unit_cost, "unit_cost"))
        if self.cost_behavior not in (None, CostBehavior.FIXED.value, CostBehavior.VARIABLE.value):
            raise FinanceInputError(f"unknown cost_behavior: {self.cost_behavior!r}")
        if self.category not in {c.value for c in CostCategory}:
            raise FinanceInputError(f"unknown category: {self.category!r}")
        start = optional_int(self.start_month, "start_month", 0, MAX_MONTHS)
        end = optional_int(self.end_month, "end_month", 0, MAX_MONTHS)
        if start is not None and end is not None and end < start:
            raise FinanceInputError("end_month cannot be before start_month")

    @property
    def total(self) -> Optional[Decimal]:
        """Rounded line total, or ``None`` when the unit cost is unknown."""
        if self.unit_cost is None:
            return None
        return round_money(mul(self.quantity, self.unit_cost))

    @property
    def label(self) -> dict[str, Any]:
        return {"id": self.id, "description": self.description, "category": self.category}


@dataclass(frozen=True)
class FinancialInputs:
    """Everything the engine needs, as plain validated values (``None`` = unknown)."""

    lines: tuple[CostLine, ...] = ()
    currency: str = "USD"
    bid_price: Optional[Decimal] = None
    duration_months: Optional[int] = None
    payment_terms_days: Optional[int] = None
    advance_payment_rate: Optional[Decimal] = None
    retention_rate: Optional[Decimal] = None
    performance_guarantee_rate: Optional[Decimal] = None
    contingency_rate: Optional[Decimal] = None
    overhead_rate: Optional[Decimal] = None
    target_margin_rate: Optional[Decimal] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "lines", tuple(self.lines))
        object.__setattr__(self, "bid_price", optional_money(self.bid_price, "bid_price"))
        object.__setattr__(self, "duration_months", optional_int(self.duration_months, "duration_months", 1, MAX_MONTHS))
        object.__setattr__(
            self, "payment_terms_days", optional_int(self.payment_terms_days, "payment_terms_days", 0)
        )
        for name in (
            "advance_payment_rate",
            "retention_rate",
            "performance_guarantee_rate",
            "contingency_rate",
            "overhead_rate",
            "target_margin_rate",
        ):
            object.__setattr__(self, name, optional_rate(getattr(self, name), name))
        advance, retention = self.advance_payment_rate, self.retention_rate
        if advance is not None and retention is not None and advance + retention > ONE:
            raise FinanceInputError("advance_payment_rate + retention_rate cannot exceed 1")


def inputs_from_model(model: Any) -> FinancialInputs:
    """Adapter from a ``FinancialModel`` (with ``cost_items``) to engine inputs.

    Duck-typed on attribute names, read-only, and the only place that knows the ORM shape.
    """
    lines = tuple(
        CostLine(
            id=item.id,
            description=item.description,
            category=_enum_value(item.category),
            quantity=item.quantity,
            unit_cost=item.unit_cost,
            cost_behavior=_enum_value(item.cost_behavior),
            verification_status=_enum_value(item.verification_status),
            start_month=item.start_month,
            end_month=item.end_month,
        )
        for item in model.cost_items
    )
    return FinancialInputs(
        lines=lines,
        currency=model.currency,
        bid_price=model.bid_price,
        duration_months=model.duration_months,
        payment_terms_days=model.payment_terms_days,
        advance_payment_rate=model.advance_payment_rate,
        retention_rate=model.retention_rate,
        performance_guarantee_rate=model.performance_guarantee_rate,
        contingency_rate=model.contingency_rate,
        overhead_rate=model.overhead_rate,
        target_margin_rate=model.target_margin_rate,
    )


# ----------------------------------------------------------------------- calculations
def active_lines(lines: Iterable[CostLine]) -> tuple[list[CostLine], int]:
    """Drop rejected lines. Returns ``(active, rejected_count)``."""
    active, rejected = [], 0
    for line in lines:
        if line.verification_status == REJECTED:
            rejected += 1
        else:
            active.append(line)
    return active, rejected


def apply_markups(
    direct: Decimal, contingency_rate: Decimal, overhead_rate: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    """``(contingency, overhead, total)`` for a direct cost. See module docstring."""
    contingency = round_money(mul(direct, contingency_rate))
    overhead = round_money(mul(direct + contingency, overhead_rate))
    return contingency, overhead, direct + contingency + overhead


@dataclass(frozen=True)
class CostResult:
    currency: str
    complete: bool
    incomplete_reasons: tuple[str, ...]
    line_count: int
    rejected_line_count: int
    known_direct_subtotal: Decimal
    direct_cost: Optional[Decimal]
    contingency_rate: Optional[Decimal]
    overhead_rate: Optional[Decimal]
    contingency: Optional[Decimal]
    overhead: Optional[Decimal]
    total_cost: Optional[Decimal]
    unknown_lines: tuple[dict[str, Any], ...]
    needs_review_lines: tuple[dict[str, Any], ...]
    unclassified_lines: tuple[dict[str, Any], ...]
    by_category: Mapping[str, Mapping[str, Any]]
    categories_without_lines: tuple[str, ...]
    fixed_cost: Optional[Decimal]
    variable_cost: Optional[Decimal]

    def as_dict(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "complete": self.complete,
            "incomplete_reasons": list(self.incomplete_reasons),
            "line_count": self.line_count,
            "rejected_line_count": self.rejected_line_count,
            "known_direct_subtotal": fmt_money(self.known_direct_subtotal),
            "direct_cost": fmt_money(self.direct_cost),
            "contingency_rate": fmt_rate(self.contingency_rate),
            "overhead_rate": fmt_rate(self.overhead_rate),
            "contingency": fmt_money(self.contingency),
            "overhead": fmt_money(self.overhead),
            "total_cost": fmt_money(self.total_cost),
            "fixed_cost": fmt_money(self.fixed_cost),
            "variable_cost": fmt_money(self.variable_cost),
            "unknown_lines": [dict(x) for x in self.unknown_lines],
            "needs_review_lines": [dict(x) for x in self.needs_review_lines],
            "unclassified_lines": [dict(x) for x in self.unclassified_lines],
            "by_category": {k: dict(v) for k, v in self.by_category.items()},
            "categories_without_lines": list(self.categories_without_lines),
        }


def calculate_cost_model(
    lines: Sequence[CostLine],
    contingency_rate: Optional[Decimal],
    overhead_rate: Optional[Decimal],
    currency: str = "USD",
) -> CostResult:
    """Build up the project cost. Never raises for *missing* data, only for *invalid* data."""
    contingency_rate = optional_rate(contingency_rate, "contingency_rate")
    overhead_rate = optional_rate(overhead_rate, "overhead_rate")
    active, rejected = active_lines(lines)

    reasons: list[str] = []
    unknown, review, unclassified = [], [], []
    known_subtotal = fixed_direct = ZERO
    per_category: dict[str, dict[str, Any]] = {}

    for line in active:
        bucket = per_category.setdefault(
            line.category, {"known_subtotal": ZERO, "line_count": 0, "unknown_line_count": 0}
        )
        bucket["line_count"] += 1
        if line.verification_status in NEEDS_REVIEW_STATUSES:
            review.append({**line.label, "verification_status": line.verification_status})
        total = line.total
        if total is None:
            bucket["unknown_line_count"] += 1
            unknown.append({**line.label, "reason": "unit_cost is unknown"})
            continue
        known_subtotal += total
        bucket["known_subtotal"] += total
        if line.cost_behavior == CostBehavior.FIXED.value:
            fixed_direct += total
        elif line.cost_behavior is None:
            unclassified.append({**line.label, "total": fmt_money(total)})

    if not active:
        reasons.append("no cost lines")
    if unknown:
        reasons.append(f"{len(unknown)} cost line(s) have an unknown unit cost")
    if contingency_rate is None:
        reasons.append("contingency_rate is unknown")
    if overhead_rate is None:
        reasons.append("overhead_rate is unknown")

    direct = known_subtotal if active and not unknown else None
    contingency = overhead = total_cost = fixed_cost = variable_cost = None
    if direct is not None and contingency_rate is not None and overhead_rate is not None:
        contingency, overhead, total_cost = apply_markups(direct, contingency_rate, overhead_rate)
        if not unclassified:
            _, _, fixed_cost = apply_markups(fixed_direct, contingency_rate, overhead_rate)
            variable_cost = total_cost - fixed_cost

    return CostResult(
        currency=currency,
        complete=not reasons,
        incomplete_reasons=tuple(reasons),
        line_count=len(active),
        rejected_line_count=rejected,
        known_direct_subtotal=known_subtotal,
        direct_cost=direct,
        contingency_rate=contingency_rate,
        overhead_rate=overhead_rate,
        contingency=contingency,
        overhead=overhead,
        total_cost=total_cost,
        unknown_lines=tuple(unknown),
        needs_review_lines=tuple(review),
        unclassified_lines=tuple(unclassified),
        by_category={
            cat: {
                "known_subtotal": fmt_money(v["known_subtotal"]),
                "line_count": v["line_count"],
                "unknown_line_count": v["unknown_line_count"],
            }
            for cat, v in sorted(per_category.items())
        },
        # Informational (e.g. "no insurance lines yet"); does not by itself make the model incomplete.
        categories_without_lines=tuple(
            c.value for c in CostCategory if c.value not in per_category and c is not CostCategory.OTHER
        ),
        fixed_cost=fixed_cost,
        variable_cost=variable_cost,
    )
