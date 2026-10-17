"""Bid pricing: suggested price from a target margin, and the margin a given price achieves.

Definitions
-----------
*Margin is margin on price* (profit as a share of the price), not markup on cost::

    suggested_price = ceil_to_cent( total_cost / (1 - target_margin_rate) )
    profit          = bid_price - total_cost
    margin_rate     = profit / bid_price          (4 dp, half-up; may be negative)
    markup_rate     = profit / total_cost         (4 dp, half-up; None when total_cost is 0)
    meets_target    = profit >= target_margin_rate * bid_price      (exact, unrounded)

The suggested price is rounded *up* (``ROUND_CEILING``) to the cent so the margin it achieves
is never below the target because of rounding. ``total_cost`` already contains contingency and
overhead (see ``cost_model``), so profit is after both.

Two modes, chosen by whether a bid price is supplied:
* no ``bid_price``: only ``suggested_price`` is produced (outcome ``no_bid_price``);
* ``bid_price`` given: the achieved profit and margin are evaluated against the target; the
  suggested price is still reported for comparison.

Unknown / degenerate inputs
---------------------------
* Costs incomplete -> no suggested price, no profit, no margin; outcome ``incomplete_costs``.
  An incomplete project is never reported as profitable.
* ``target_margin_rate`` unknown -> no suggested price (never assumed 0%).
* ``target_margin_rate == 1`` -> price would be infinite: no suggested price, with a reason.
* ``bid_price == 0`` -> margin is undefined (``None``) instead of dividing by zero.

Outcomes: ``incomplete_costs``, ``no_bid_price``, ``loss``, ``no_profit``,
``profit_target_unknown``, ``below_target``, ``meets_target``.

Limitations: prices exclude tax; no competitor prices are modelled or invented; the price is a
calculation to support a decision, not a recommendation to bid.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
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
    optional_rate,
    round_money,
    round_rate,
)

OUTCOMES = (
    "incomplete_costs",
    "no_bid_price",
    "loss",
    "no_profit",
    "profit_target_unknown",
    "below_target",
    "meets_target",
)


def suggest_price(total_cost: Optional[Decimal], target_margin_rate: Optional[Decimal]) -> Optional[Decimal]:
    """Price that achieves the target margin on price, rounded up to the cent.

    Returns ``None`` when the cost or the margin is unknown, or when the margin is 100%.
    """
    total_cost = optional_money(total_cost, "total_cost")
    target_margin_rate = optional_rate(target_margin_rate, "target_margin_rate")
    if total_cost is None or target_margin_rate is None or target_margin_rate >= ONE:
        return None
    return round_money(div(total_cost, ONE - target_margin_rate), ROUND_CEILING)


@dataclass(frozen=True)
class PricingResult:
    outcome: str
    reasons: tuple[str, ...]
    currency: str
    total_cost: Optional[Decimal]
    target_margin_rate: Optional[Decimal]
    suggested_price: Optional[Decimal]
    bid_price: Optional[Decimal]
    profit: Optional[Decimal]
    margin_rate: Optional[Decimal]
    markup_rate: Optional[Decimal]
    meets_target_margin: Optional[bool]
    shortfall_to_suggested_price: Optional[Decimal]

    def as_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "reasons": list(self.reasons),
            "currency": self.currency,
            "total_cost": fmt_money(self.total_cost),
            "target_margin_rate": fmt_rate(self.target_margin_rate),
            "suggested_price": fmt_money(self.suggested_price),
            "bid_price": fmt_money(self.bid_price),
            "profit": fmt_money(self.profit),
            "margin_rate": fmt_rate(self.margin_rate),
            "markup_rate": fmt_rate(self.markup_rate),
            "meets_target_margin": self.meets_target_margin,
            "shortfall_to_suggested_price": fmt_money(self.shortfall_to_suggested_price),
        }


def calculate_bid_pricing(
    cost: CostResult,
    bid_price: Optional[Decimal],
    target_margin_rate: Optional[Decimal],
) -> PricingResult:
    bid_price = optional_money(bid_price, "bid_price")
    target = optional_rate(target_margin_rate, "target_margin_rate")
    total = cost.total_cost  # None when the cost model is incomplete

    reasons: list[str] = []
    if total is None:
        reasons.append("total cost is incomplete: " + "; ".join(cost.incomplete_reasons))
    if target is None:
        reasons.append("target_margin_rate is unknown")
    elif target >= ONE:
        reasons.append("a target margin of 100% cannot be priced")
    suggested = suggest_price(total, target)

    profit = margin = markup = meets = shortfall = None
    if total is None:
        outcome = "incomplete_costs"
    elif bid_price is None:
        outcome = "no_bid_price"
        reasons.append("bid_price is not set")
    else:
        profit = bid_price - total
        if bid_price > ZERO:
            margin = round_rate(div(profit, bid_price))
        else:
            reasons.append("bid_price is 0: margin is undefined")
        if total > ZERO:
            markup = round_rate(div(profit, total))
        if target is not None:
            meets = profit >= mul(target, bid_price)
        if suggested is not None and bid_price < suggested:
            shortfall = suggested - bid_price

        if profit < ZERO:
            outcome = "loss"
        elif profit == ZERO:
            outcome = "no_profit"
        elif target is None:
            outcome = "profit_target_unknown"
        else:
            outcome = "meets_target" if meets else "below_target"

    return PricingResult(
        outcome=outcome,
        reasons=tuple(reasons),
        currency=cost.currency,
        total_cost=total,
        target_margin_rate=target,
        suggested_price=suggested,
        bid_price=bid_price,
        profit=profit,
        margin_rate=margin,
        markup_rate=markup,
        meets_target_margin=meets,
        shortfall_to_suggested_price=shortfall,
    )
