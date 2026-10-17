"""Break-even analysis for a fixed-price contract (FR-21).

Model
-----
A tender is a fixed price ``P`` for the whole scope. Revenue is earned in proportion to
progress ``x`` (0..1). *Fixed* costs ``F`` are committed in full whatever the progress;
*variable* costs ``V`` (full-scope amount) grow in proportion to progress. Both include their
share of contingency and overhead (see ``cost_model``). Profit at progress ``x``::

    profit(x) = P*x - F - V*x      =>   break-even when  x* = F / (P - V)

Reported as::

    contribution                = P - V
    contribution_margin_ratio   = (P - V) / P                      (4 dp)
    break_even_revenue          = F / contribution_margin_ratio = F * P / (P - V)
    break_even_progress         = break_even_revenue / P = F / (P - V)       (4 dp)
    margin_of_safety            = 1 - break_even_progress          (4 dp, may be negative)
    profit_at_full_delivery     = P - (F + V)

If ``break_even_progress > 1`` the contract loses money even when 100% delivered
(equivalently ``P < F + V``); status is ``not_reached_within_contract``.

Statuses (first match wins; every blocking cause is also listed in ``reasons``)
-------------------------------------------------------------------------------
``incomplete_costs``   cost model incomplete -> no figures
``unclassified_costs`` some priced lines have no fixed/variable classification -> no figures;
                       they are listed, never assumed fixed or variable
``no_bid_price``       price unknown
``zero_bid_price``     price is 0 (the ratio would divide by zero)
``no_break_even``      P - V <= 0: variable costs alone consume the price, fixed costs can
                       never be recovered
``not_reached_within_contract``  break-even revenue exceeds the price
``ok``

Limitations: this is a *progress* break-even for a fixed-price contract, not a cash break-even
(see ``cashflow`` for timing); fixed costs are assumed fully committed and variable costs
strictly proportional to progress; performance guarantees and tax are not included.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Optional

from app.services.finance.cost_model import (
    ONE,
    ZERO,
    CostResult,
    div,
    fmt_money,
    fmt_rate,
    mul,
    optional_money,
    round_money,
    round_rate,
)

STATUSES = (
    "incomplete_costs",
    "unclassified_costs",
    "no_bid_price",
    "zero_bid_price",
    "no_break_even",
    "not_reached_within_contract",
    "ok",
)


@dataclass(frozen=True)
class BreakEvenResult:
    status: str
    reasons: tuple[str, ...]
    currency: str
    bid_price: Optional[Decimal]
    fixed_cost: Optional[Decimal]
    variable_cost: Optional[Decimal]
    contribution: Optional[Decimal]
    contribution_margin_ratio: Optional[Decimal]
    break_even_revenue: Optional[Decimal]
    break_even_progress: Optional[Decimal]
    margin_of_safety: Optional[Decimal]
    profit_at_full_delivery: Optional[Decimal]
    reached_within_contract: Optional[bool]
    unclassified_lines: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reasons": list(self.reasons),
            "currency": self.currency,
            "bid_price": fmt_money(self.bid_price),
            "fixed_cost": fmt_money(self.fixed_cost),
            "variable_cost": fmt_money(self.variable_cost),
            "contribution": fmt_money(self.contribution),
            "contribution_margin_ratio": fmt_rate(self.contribution_margin_ratio),
            "break_even_revenue": fmt_money(self.break_even_revenue),
            "break_even_progress": fmt_rate(self.break_even_progress),
            "margin_of_safety": fmt_rate(self.margin_of_safety),
            "profit_at_full_delivery": fmt_money(self.profit_at_full_delivery),
            "reached_within_contract": self.reached_within_contract,
            "unclassified_lines": [dict(x) for x in self.unclassified_lines],
        }


def calculate_break_even(cost: CostResult, bid_price: Optional[Decimal]) -> BreakEvenResult:
    price = optional_money(bid_price, "bid_price")
    reasons: list[str] = []
    status: Optional[str] = None

    if not cost.complete:
        status = "incomplete_costs"
        reasons.append("cost model is incomplete: " + "; ".join(cost.incomplete_reasons))
    if cost.complete and cost.unclassified_lines:
        status = status or "unclassified_costs"
        reasons.append(
            f"{len(cost.unclassified_lines)} cost line(s) are not classified as fixed or variable"
        )
    if price is None:
        status = status or "no_bid_price"
        reasons.append("bid_price is unknown")
    elif price == ZERO:
        status = status or "zero_bid_price"
        reasons.append("bid_price is 0: break-even is undefined")

    def empty(final_status: str) -> BreakEvenResult:
        return BreakEvenResult(
            status=final_status,
            reasons=tuple(reasons),
            currency=cost.currency,
            bid_price=price,
            fixed_cost=cost.fixed_cost,
            variable_cost=cost.variable_cost,
            contribution=None,
            contribution_margin_ratio=None,
            break_even_revenue=None,
            break_even_progress=None,
            margin_of_safety=None,
            profit_at_full_delivery=None,
            reached_within_contract=None,
            unclassified_lines=cost.unclassified_lines,
        )

    if status is not None:
        return empty(status)

    fixed, variable = cost.fixed_cost, cost.variable_cost
    assert price is not None and fixed is not None and variable is not None  # guaranteed above
    contribution = price - variable
    profit_full = price - (fixed + variable)

    if contribution <= ZERO:
        reasons.append("variable costs are not below the bid price: fixed costs can never be recovered")
        return replace(
            empty("no_break_even"), contribution=contribution, profit_at_full_delivery=profit_full
        )

    ratio = div(contribution, price)
    progress_exact = div(fixed, contribution)
    reached = progress_exact <= ONE
    if not reached:
        reasons.append("break-even revenue exceeds the bid price: the contract loses money as priced")
    return BreakEvenResult(
        status="ok" if reached else "not_reached_within_contract",
        reasons=tuple(reasons),
        currency=cost.currency,
        bid_price=price,
        fixed_cost=fixed,
        variable_cost=variable,
        contribution=contribution,
        contribution_margin_ratio=round_rate(ratio),
        break_even_revenue=round_money(mul(progress_exact, price)),
        break_even_progress=round_rate(progress_exact),
        margin_of_safety=round_rate(ONE - progress_exact),
        profit_at_full_delivery=profit_full,
        reached_within_contract=reached,
        unclassified_lines=(),
    )
