"""Scenario calculation: re-run the finance pipeline on a base model with overrides (FR-24).

Like the rest of ``services/finance`` this module is *pure*: no database, no clock, no
randomness. A scenario is the base model's inputs plus a mapping of ``overrides``; the result
is the full ``calculate_financial_results`` output for the changed inputs, plus a comparison
with the unchanged base so the effect of the scenario is explicit.

Supported overrides (anything else is rejected, never silently ignored)
----------------------------------------------------------------------
Scalar inputs, replacing the base value::

    bid_price, duration_months, payment_terms_days, advance_payment_rate, retention_rate,
    performance_guarantee_rate, contingency_rate, overhead_rate, target_margin_rate

An explicit ``null`` sets the input to *unknown* (it is never turned into 0).

``cost_multipliers``: ``{"<category>": "<factor>"}`` multiplies the unit cost of every cost
line of that category by a non-negative factor (``"1.10"`` = +10%), e.g. a materials price
rise. Lines with an unknown unit cost stay unknown. Rejected lines are untouched (they are
excluded from the totals anyway). Each unit cost is rounded half-up to the cent.

Values may be numbers or numeric strings; floats are converted via ``str`` so no binary noise
enters the calculation. Rates are fractions (0.10 = 10%).

Results
-------
``calculate_scenario`` returns the same top-level scalar keys as ``calculate_financial_results``
(so the stored-scenario comparison keeps working) plus nested detail::

    overrides_applied      the validated, normalised overrides
    base                   scalar headline metrics of the unchanged base model
    deltas_vs_base         scenario minus base for money metrics and the margin rate; ``None``
                           when either side is unknown (an unknown is never treated as 0)
    provenance             engine version and a SHA-256 fingerprint of the exact inputs used,
                           so a stored result can be checked against its inputs later

Limitations: only the overrides above are modelled; there is no probability weighting,
sensitivity sweep or tax/escalation. A scenario with no overrides reproduces the base exactly.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import fields, replace
from decimal import Decimal
from typing import Any, Optional

from app.models.financial_model import CostCategory
from app.services.finance.cashflow import calculate_financial_results
from app.services.finance.cost_model import (
    ENGINE_VERSION,
    CostLine,
    FinanceInputError,
    FinancialInputs,
    fmt_money,
    fmt_rate,
    mul,
    round_money,
    to_decimal,
)

SCALAR_OVERRIDES = (
    "bid_price",
    "duration_months",
    "payment_terms_days",
    "advance_payment_rate",
    "retention_rate",
    "performance_guarantee_rate",
    "contingency_rate",
    "overhead_rate",
    "target_margin_rate",
)
COLLECTION_OVERRIDES = ("cost_multipliers",)
ALLOWED_OVERRIDES = SCALAR_OVERRIDES + COLLECTION_OVERRIDES

INTEGER_OVERRIDES = ("duration_months", "payment_terms_days")  # whole numbers, kept as given
MAX_MULTIPLIER = Decimal("1000")

# Money metrics compared with the base (string values in the results dict).
_MONEY_DELTA_KEYS = (
    "total_cost",
    "profit",
    "suggested_price",
    "bid_price",
    "peak_funding_requirement",
    "closing_balance",
)
_RATE_DELTA_KEYS = ("margin_rate",)
_BASE_KEYS = _MONEY_DELTA_KEYS + _RATE_DELTA_KEYS + (
    "price_basis",
    "pricing_outcome",
    "break_even_status",
    "cash_flow_status",
)


# ------------------------------------------------------------------------ validation
def _normalise_multipliers(value: Any) -> dict[str, Decimal]:
    if not isinstance(value, Mapping):
        raise FinanceInputError("cost_multipliers must be an object of category -> factor")
    valid = {c.value for c in CostCategory}
    out: dict[str, Decimal] = {}
    for category, factor in value.items():
        if category not in valid:
            raise FinanceInputError(f"cost_multipliers: unknown category {category!r}")
        number = to_decimal(factor, f"cost_multipliers[{category}]")
        if number < 0:
            raise FinanceInputError(f"cost_multipliers[{category}] cannot be negative")
        if number > MAX_MULTIPLIER:
            raise FinanceInputError(f"cost_multipliers[{category}] cannot exceed {MAX_MULTIPLIER}")
        out[category] = number
    return out


def validate_overrides(overrides: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """Return a normalised copy of ``overrides`` or raise ``FinanceInputError``.

    Money and rate values are converted to canonical decimal strings (``0.15`` and ``"0.15"``
    both become ``"0.15"``; ``null`` stays ``null`` = unknown). Their numeric *ranges* are
    enforced by ``FinancialInputs`` when the overrides are applied, so there is one source of
    truth. Whole-number fields (months, days) are validated there too.
    """
    if overrides is None:
        return {}
    if not isinstance(overrides, Mapping):
        raise FinanceInputError("overrides must be an object")
    unknown = sorted(str(k) for k in set(overrides) - set(ALLOWED_OVERRIDES))
    if unknown:
        raise FinanceInputError(
            "unsupported override(s): " + ", ".join(repr(k) for k in unknown)
            + "; supported: " + ", ".join(ALLOWED_OVERRIDES)
        )
    clean: dict[str, Any] = {}
    for key, value in overrides.items():
        if key == "cost_multipliers":
            clean[key] = _normalise_multipliers(value)
        elif key in INTEGER_OVERRIDES or value is None:
            clean[key] = value
        else:
            clean[key] = format(to_decimal(value, key), "f")
    return clean


# ---------------------------------------------------------------------------- apply
def apply_overrides(base: FinancialInputs, overrides: Optional[Mapping[str, Any]]) -> FinancialInputs:
    """New ``FinancialInputs`` with the overrides applied. ``base`` is never modified."""
    clean = validate_overrides(overrides)
    scalars = {k: v for k, v in clean.items() if k in SCALAR_OVERRIDES}
    lines = base.lines
    multipliers = clean.get("cost_multipliers")
    if multipliers:
        lines = tuple(_scale_line(line, multipliers) for line in base.lines)
    # Re-running __post_init__ validates ranges (rates 0..1, advance + retention <= 1, ...).
    return replace(base, lines=lines, **scalars)


def _scale_line(line: CostLine, multipliers: Mapping[str, Decimal]) -> CostLine:
    factor = multipliers.get(line.category)
    if factor is None or line.unit_cost is None or line.verification_status == "Rejected":
        return line
    return replace(line, unit_cost=round_money(mul(line.unit_cost, factor)))


# ---------------------------------------------------------------------- fingerprint
def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in sorted(value.items())}
    if hasattr(value, "__dataclass_fields__"):
        return {f.name: _jsonable(getattr(value, f.name)) for f in fields(value)}
    return value


def inputs_fingerprint(inputs: FinancialInputs) -> str:
    """SHA-256 of the exact engine inputs (canonical JSON). Same inputs -> same fingerprint."""
    payload = json.dumps(_jsonable(inputs), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------- deltas
def _delta(new: Optional[str], old: Optional[str], formatter) -> Optional[str]:
    """``new - old`` as a formatted string; ``None`` if either side is unknown."""
    if new is None or old is None:
        return None
    return formatter(Decimal(new) - Decimal(old))


def _deltas(scenario: Mapping[str, Any], base: Mapping[str, Any]) -> dict[str, Optional[str]]:
    out: dict[str, Optional[str]] = {}
    for key in _MONEY_DELTA_KEYS:
        out[key] = _delta(scenario.get(key), base.get(key), fmt_money)
    for key in _RATE_DELTA_KEYS:
        out[key] = _delta(scenario.get(key), base.get(key), fmt_rate)
    return out


# ------------------------------------------------------------------------- entry point
def calculate_scenario(base: FinancialInputs, overrides: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    """Calculate a scenario and compare it with the unchanged base. Pure and deterministic.

    Raises ``FinanceInputError`` for unsupported or invalid overrides, or when the overridden
    inputs are inconsistent (e.g. advance + retention above 100%).
    """
    clean = validate_overrides(overrides)
    scenario_inputs = apply_overrides(base, clean)

    base_results = calculate_financial_results(base)
    results = calculate_financial_results(scenario_inputs)

    results["overrides_applied"] = _jsonable(clean)
    results["base"] = {key: base_results.get(key) for key in _BASE_KEYS}
    results["deltas_vs_base"] = _deltas(results, base_results)
    results["provenance"] = {
        "engine_version": ENGINE_VERSION,
        "inputs_fingerprint": inputs_fingerprint(scenario_inputs),
        "base_inputs_fingerprint": inputs_fingerprint(base),
    }
    return results
