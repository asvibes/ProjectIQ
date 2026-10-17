"""Monthly cash flow and the end-to-end finance pipeline (FR-21, FR-22).

This is the last stage of ``cost_model -> bid_pricing -> breakeven -> cashflow``, so the
aggregator ``calculate_financial_results`` lives here.

Timeline: whole months, month 0 = project start. No calendar dates, no discounting.

Outflows (costs)
----------------
A scheduled line (both ``start_month`` and ``end_month`` set, line total known) is spread
evenly over ``start_month..end_month`` inclusive in whole cents (largest-remainder: no
negative months, parts sum exactly to the line total). Contingency and overhead are added per
month by allocating the *total* loaded cost across months in proportion to each month's direct
cost, so the series sums exactly to the ``cost_model`` total for the scheduled lines.
Lines with an unknown cost or missing timing are never silently spread or zeroed: they are
listed (``unknown_lines`` / ``unscheduled_lines``) and the result becomes ``partial``.
Rejected lines are excluded by rule (as in ``cost_model``).

Inflows (receipts) for price ``P`` and duration ``D`` months
-----------------------------------------------------------
* Billing: ``P`` is billed evenly over months ``0..D-1`` (the model has no milestones).
* Payment lag: ``lag = ceil(payment_terms_days / 30)`` months (30-day months, 0 days -> 0).
  Invoice for month k is received in month ``k + lag``.
* Retention: ``R = round_money(P * retention_rate)`` is withheld pro rata from the invoices
  and released in full in month ``D + lag`` (one month after the final invoice falls due).
  The data model has no defects-liability period; this is a stated assumption.
* Advance: ``A = round_money(P * advance_payment_rate)``, received in month 0 (not delayed
  by ``lag``) and recovered pro rata from the invoices after retention. ``A`` is capped at
  ``P - R`` so advance plus retention can never exceed the price by a rounding cent.
* Net payment for invoice k = invoice_k - retention_k - advance_recovery_k  (never negative).
* Receipts always total exactly ``P``; the closing balance equals ``P - total_cost`` when all
  costs are scheduled.
* ``performance_guarantee_amount = round_money(P * performance_guarantee_rate)`` is reported as
  exposure only; no fee is charged (no fee input exists) and it is not a cash movement.

Headline metrics
----------------
``cumulative`` is the running sum of ``receipts - costs``. ``cumulative_low_point`` is its
minimum over the horizon; ``peak_funding_requirement = max(0, -cumulative_low_point)``, with
the (first) month it occurs. Comparing this with working capital is a later feature.

Statuses
--------
``insufficient_inputs``  something required is unknown (price, duration, payment terms,
                         advance/retention/contingency/overhead rate): no series, and the
                         unknown inputs are listed. An unknown input is never treated as 0.
``partial``              series produced from known, scheduled lines only; headline metrics
                         are withheld (``None``) because they would be understated.
``ok``                   all costs known and scheduled.

Limitations: even spreading, even billing, 30-day months; no tax, escalation, financing
cost, interest on cash, variations or milestone billing.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from app.services.finance.bid_pricing import PricingResult, calculate_bid_pricing
from app.services.finance.breakeven import BreakEvenResult, calculate_break_even
from app.services.finance.cost_model import (
    CENT,
    ENGINE_VERSION,
    MAX_MONTHS,
    ZERO,
    CostLine,
    CostResult,
    FinanceInputError,
    FinancialInputs,
    active_lines,
    apply_markups,
    calculate_cost_model,
    div,
    fmt_money,
    mul,
    optional_int,
    optional_money,
    optional_rate,
    round_money,
)

DAYS_PER_MONTH = 30


# ------------------------------------------------------------------------- allocation
def _cents(amount: Decimal) -> int:
    return int(div(amount, CENT).to_integral_value())


def _from_cents(cents: int) -> Decimal:
    return mul(Decimal(cents), CENT).quantize(CENT)


def allocate_cents(total: Decimal, weights: Sequence[int]) -> list[Decimal]:
    """Split ``total`` into parts proportional to integer ``weights``; parts sum exactly to total.

    Largest-remainder method on whole cents: floor every share, then give the leftover cents to
    the largest fractional remainders (ties go to the later index). All parts are >= 0 and each
    part is at most ``ceil`` of its exact share, so a part can never exceed a weight when
    ``total <= sum(weights)`` and weights are cent amounts.
    """
    if total < 0 or any(w < 0 for w in weights):
        raise ValueError("allocation needs non-negative totals and weights")
    total_cents = _cents(round_money(total))
    weight_sum = sum(weights)
    if not weights:
        if total_cents:
            raise ValueError("cannot allocate a non-zero total over no periods")
        return []
    if weight_sum == 0:
        if total_cents:
            raise ValueError("cannot allocate a non-zero total over zero weights")
        return [ZERO.quantize(CENT) for _ in weights]
    floors = [total_cents * w // weight_sum for w in weights]
    remainders = [total_cents * w % weight_sum for w in weights]
    leftover = total_cents - sum(floors)
    order = sorted(range(len(weights)), key=lambda i: (remainders[i], i), reverse=True)
    for i in order[:leftover]:
        floors[i] += 1
    return [_from_cents(c) for c in floors]


def payment_lag_months(payment_terms_days: int) -> int:
    """``ceil(days / 30)`` using integer arithmetic."""
    return (payment_terms_days + DAYS_PER_MONTH - 1) // DAYS_PER_MONTH


# --------------------------------------------------------------------------- cash flow
@dataclass(frozen=True)
class CashFlowResult:
    status: str
    complete: bool
    currency: str
    missing_inputs: tuple[str, ...]
    incomplete_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    bid_price: Optional[Decimal]
    duration_months: Optional[int]
    payment_lag_months: Optional[int]
    advance_amount: Optional[Decimal]
    retention_amount: Optional[Decimal]
    performance_guarantee_amount: Optional[Decimal]
    total_costs_scheduled: Optional[Decimal]
    total_receipts: Optional[Decimal]
    closing_balance: Optional[Decimal]
    cumulative_low_point: Optional[Decimal]
    peak_funding_requirement: Optional[Decimal]
    peak_funding_month: Optional[int]
    months: tuple[dict[str, Any], ...]
    unknown_lines: tuple[dict[str, Any], ...]
    unscheduled_lines: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "complete": self.complete,
            "currency": self.currency,
            "missing_inputs": list(self.missing_inputs),
            "incomplete_reasons": list(self.incomplete_reasons),
            "warnings": list(self.warnings),
            "bid_price": fmt_money(self.bid_price),
            "duration_months": self.duration_months,
            "payment_lag_months": self.payment_lag_months,
            "advance_amount": fmt_money(self.advance_amount),
            "retention_amount": fmt_money(self.retention_amount),
            "performance_guarantee_amount": fmt_money(self.performance_guarantee_amount),
            "total_costs_scheduled": fmt_money(self.total_costs_scheduled),
            "total_receipts": fmt_money(self.total_receipts),
            "closing_balance": fmt_money(self.closing_balance),
            "cumulative_low_point": fmt_money(self.cumulative_low_point),
            "peak_funding_requirement": fmt_money(self.peak_funding_requirement),
            "peak_funding_month": self.peak_funding_month,
            "months": [dict(m) for m in self.months],
            "unknown_lines": [dict(x) for x in self.unknown_lines],
            "unscheduled_lines": [dict(x) for x in self.unscheduled_lines],
        }


def calculate_cash_flow(
    lines: Sequence[CostLine],
    *,
    bid_price: Optional[Decimal],
    duration_months: Optional[int],
    payment_terms_days: Optional[int],
    advance_payment_rate: Optional[Decimal],
    retention_rate: Optional[Decimal],
    contingency_rate: Optional[Decimal],
    overhead_rate: Optional[Decimal],
    performance_guarantee_rate: Optional[Decimal] = None,
    currency: str = "USD",
) -> CashFlowResult:
    """Monthly cash flow. Raises ``FinanceInputError`` only for invalid (not missing) inputs."""
    price = optional_money(bid_price, "bid_price")
    duration = optional_int(duration_months, "duration_months", 1, MAX_MONTHS)
    terms = optional_int(payment_terms_days, "payment_terms_days", 0)
    advance_rate = optional_rate(advance_payment_rate, "advance_payment_rate")
    retention = optional_rate(retention_rate, "retention_rate")
    cont_rate = optional_rate(contingency_rate, "contingency_rate")
    ovh_rate = optional_rate(overhead_rate, "overhead_rate")
    guarantee_rate = optional_rate(performance_guarantee_rate, "performance_guarantee_rate")
    if advance_rate is not None and retention is not None and advance_rate + retention > 1:
        raise FinanceInputError("advance_payment_rate + retention_rate cannot exceed 1")

    required = {
        "bid_price": price,
        "duration_months": duration,
        "payment_terms_days": terms,
        "advance_payment_rate": advance_rate,
        "retention_rate": retention,
        "contingency_rate": cont_rate,
        "overhead_rate": ovh_rate,
    }
    missing = tuple(name for name, value in required.items() if value is None)
    active, _ = active_lines(lines)
    guarantee = round_money(mul(price, guarantee_rate)) if price is not None and guarantee_rate is not None else None

    def blank(status: str, reasons: tuple[str, ...] = ()) -> CashFlowResult:
        return CashFlowResult(
            status=status, complete=False, currency=currency, missing_inputs=missing,
            incomplete_reasons=reasons, warnings=(), bid_price=price, duration_months=duration,
            payment_lag_months=None if terms is None else payment_lag_months(terms),
            advance_amount=None, retention_amount=None, performance_guarantee_amount=guarantee,
            total_costs_scheduled=None, total_receipts=None, closing_balance=None,
            cumulative_low_point=None, peak_funding_requirement=None, peak_funding_month=None,
            months=(), unknown_lines=(), unscheduled_lines=(),
        )

    if missing:
        return blank("insufficient_inputs", ("unknown inputs: " + ", ".join(missing),))
    assert price is not None and duration is not None and terms is not None
    assert advance_rate is not None and retention is not None
    assert cont_rate is not None and ovh_rate is not None

    # ---- classify lines -------------------------------------------------------------
    unknown, unscheduled = [], []
    direct_by_month: dict[int, int] = {}  # month -> direct cost in cents
    reasons: list[str] = []
    for line in active:
        total = line.total
        if total is None:
            unknown.append({**line.label, "reason": "unit_cost is unknown"})
            continue
        if line.start_month is None or line.end_month is None:
            unscheduled.append({**line.label, "total": fmt_money(total), "reason": "start_month/end_month not both set"})
            continue
        span = line.end_month - line.start_month + 1
        for offset, part in enumerate(allocate_cents(total, [1] * span)):
            month = line.start_month + offset
            direct_by_month[month] = direct_by_month.get(month, 0) + _cents(part)
    if not active:
        reasons.append("no cost lines")
    if unknown:
        reasons.append(f"{len(unknown)} cost line(s) have an unknown unit cost")
    if unscheduled:
        reasons.append(f"{len(unscheduled)} cost line(s) have no schedule and are excluded from the series")

    # ---- cost outflows by month -----------------------------------------------------
    direct_total = _from_cents(sum(direct_by_month.values()))
    _, _, loaded_total = apply_markups(direct_total, cont_rate, ovh_rate)
    cost_months = sorted(direct_by_month)
    cost_weights = [direct_by_month[m] for m in cost_months]
    loaded_parts = allocate_cents(loaded_total, cost_weights) if cost_months else []
    costs_by_month = dict(zip(cost_months, loaded_parts))

    # ---- receipts by month ----------------------------------------------------------
    lag = payment_lag_months(terms)
    invoices = allocate_cents(price, [1] * duration)
    retention_total = round_money(mul(price, retention))
    retained = allocate_cents(retention_total, [_cents(i) for i in invoices])
    after_retention = [i - r for i, r in zip(invoices, retained)]
    advance = min(round_money(mul(price, advance_rate)), price - retention_total)
    recovery = allocate_cents(advance, [_cents(x) for x in after_retention])

    receipts_by_month: dict[int, Decimal] = {}

    def receive(month: int, amount: Decimal) -> None:
        if amount:
            receipts_by_month[month] = receipts_by_month.get(month, ZERO) + amount

    receive(0, advance)
    for k, (inv_after, rec) in enumerate(zip(after_retention, recovery)):
        receive(k + lag, inv_after - rec)
    receive(duration + lag, retention_total)

    # ---- series ---------------------------------------------------------------------
    horizon = max([duration, *(m + 1 for m in costs_by_month), *(m + 1 for m in receipts_by_month)])
    if cost_months and cost_months[-1] >= duration:
        reasons_warning = f"costs are scheduled after month {duration - 1} (beyond duration_months)"
    else:
        reasons_warning = None
    months, cumulative = [], ZERO
    low, low_month = None, None
    total_costs = total_receipts = ZERO
    for m in range(horizon):
        cost_m = costs_by_month.get(m, ZERO)
        receipt_m = receipts_by_month.get(m, ZERO)
        net = receipt_m - cost_m
        cumulative += net
        total_costs += cost_m
        total_receipts += receipt_m
        if low is None or cumulative < low:
            low, low_month = cumulative, m
        months.append(
            {
                "month": m,
                "costs": fmt_money(cost_m),
                "receipts": fmt_money(receipt_m),
                "net": fmt_money(net),
                "cumulative": fmt_money(cumulative),
            }
        )

    complete = not reasons
    peak = max(ZERO, -low) if low is not None else None
    return CashFlowResult(
        status="ok" if complete else "partial",
        complete=complete,
        currency=currency,
        missing_inputs=(),
        incomplete_reasons=tuple(reasons),
        warnings=(reasons_warning,) if reasons_warning else (),
        bid_price=price,
        duration_months=duration,
        payment_lag_months=lag,
        advance_amount=advance,
        retention_amount=retention_total,
        performance_guarantee_amount=guarantee,
        total_costs_scheduled=total_costs,
        total_receipts=total_receipts,
        # Headline numbers would be understated while costs are missing, so they are withheld.
        closing_balance=cumulative if complete else None,
        cumulative_low_point=low if complete else None,
        peak_funding_requirement=peak if complete else None,
        peak_funding_month=(low_month if peak and complete else None),
        months=tuple(months),
        unknown_lines=tuple(unknown),
        unscheduled_lines=tuple(unscheduled),
    )


# -------------------------------------------------------------------------- pipeline
def calculate_financial_results(inputs: FinancialInputs) -> dict[str, Any]:
    """Run all four stages and return one JSON-safe dict for ``FinancialModel.results``.

    Top-level scalar keys (str / bool / int / None) feed the existing scenario comparison
    (``scenario_compare`` only reads top-level scalars); nested dicts hold the detail. The
    caller stores ``calculated_at`` and ``engine_version`` (= ``ENGINE_VERSION``).

    Price basis: the stored ``bid_price`` if set, otherwise the suggested price (never when
    costs are incomplete), labelled in ``price_basis``.
    """
    cost: CostResult = calculate_cost_model(
        inputs.lines, inputs.contingency_rate, inputs.overhead_rate, inputs.currency
    )
    pricing: PricingResult = calculate_bid_pricing(cost, inputs.bid_price, inputs.target_margin_rate)

    if inputs.bid_price is not None:
        price, basis = inputs.bid_price, "bid_price"
    elif pricing.suggested_price is not None:
        price, basis = pricing.suggested_price, "suggested_price"
    else:
        price, basis = None, "none"

    breakeven: BreakEvenResult = calculate_break_even(cost, price)
    cashflow: CashFlowResult = calculate_cash_flow(
        inputs.lines,
        bid_price=price,
        duration_months=inputs.duration_months,
        payment_terms_days=inputs.payment_terms_days,
        advance_payment_rate=inputs.advance_payment_rate,
        retention_rate=inputs.retention_rate,
        contingency_rate=inputs.contingency_rate,
        overhead_rate=inputs.overhead_rate,
        performance_guarantee_rate=inputs.performance_guarantee_rate,
        currency=inputs.currency,
    )
    pricing_d, breakeven_d, cashflow_d = pricing.as_dict(), breakeven.as_dict(), cashflow.as_dict()
    return {
        "engine_version": ENGINE_VERSION,
        "currency": inputs.currency,
        "price_basis": basis,
        "costs_complete": cost.complete,  # cost model only; see cash_flow_status for the series
        "total_cost": fmt_money(cost.total_cost),
        "direct_cost": fmt_money(cost.direct_cost),
        "known_direct_subtotal": fmt_money(cost.known_direct_subtotal),
        "suggested_price": pricing_d["suggested_price"],
        "bid_price": pricing_d["bid_price"],
        "profit": pricing_d["profit"],
        "margin_rate": pricing_d["margin_rate"],
        "pricing_outcome": pricing.outcome,
        "break_even_status": breakeven.status,
        "break_even_revenue": breakeven_d["break_even_revenue"],
        "break_even_progress": breakeven_d["break_even_progress"],
        "cash_flow_status": cashflow.status,
        "peak_funding_requirement": cashflow_d["peak_funding_requirement"],
        "peak_funding_month": cashflow.peak_funding_month,
        "closing_balance": cashflow_d["closing_balance"],
        "cost_model": cost.as_dict(),
        "bid_pricing": pricing_d,
        "break_even": breakeven_d,
        "cash_flow": cashflow_d,
    }
