"""Tests for bid pricing. Expected values are hand-derived (see comments)."""
import json
from decimal import Decimal as D

import pytest

from app.services.finance.bid_pricing import calculate_bid_pricing, suggest_price
from app.services.finance.cost_model import CostLine, FinanceInputError, calculate_cost_model


def cost(total, cont="0", ovh="0"):
    """A complete CostResult whose total is exactly ``total`` (one line, zero markups)."""
    line = CostLine(1, "x", "labour", D("1"), D(total), "variable", "Verified")
    return calculate_cost_model([line], cont, ovh)


def incomplete():
    line = CostLine(1, "x", "labour", D("1"), None, "variable", "Verified")
    return calculate_cost_model([line], "0", "0")


# ------------------------------------------------------------------ suggested price
def test_suggested_price_is_margin_on_price_not_markup():
    # 900 / (1 - 0.10) = 1000 exactly: profit 100 is 10% of the PRICE (markup would give 990).
    assert suggest_price(D("900"), D("0.10")) == D("1000.00")


def test_suggested_price_rounds_up_to_the_cent():
    # 100 / 0.7 = 142.857142... -> 142.86 (ceiling, never 142.85)
    assert suggest_price(D("100"), D("0.30")) == D("142.86")
    # 1733.08 / 0.85 = 2038.9176... -> 2038.92
    assert suggest_price(D("1733.08"), D("0.15")) == D("2038.92")


@pytest.mark.parametrize("total", ["0.01", "1", "99.99", "1733.08", "123456.79"])
@pytest.mark.parametrize("margin", ["0", "0.0001", "0.05", "0.1", "0.3333", "0.5", "0.9999"])
def test_rounding_never_leaves_margin_below_target(total, margin):
    price = suggest_price(D(total), D(margin))
    assert price - D(total) >= D(margin) * price  # exact check, no rounding of the margin
    assert price - D("0.01") - D(total) < D(margin) * (price - D("0.01"))  # and it is the lowest such cent


def test_zero_margin_prices_at_cost_and_zero_cost_prices_at_zero():
    assert suggest_price(D("250.5"), D("0")) == D("250.50")
    assert suggest_price(D("0"), D("0.2")) == D("0.00")


@pytest.mark.parametrize("total,margin", [(None, "0.1"), ("100", None), ("100", "1"), (None, None)])
def test_suggested_price_unavailable_instead_of_guessing(total, margin):
    assert suggest_price(None if total is None else D(total), None if margin is None else D(margin)) is None


@pytest.mark.parametrize("margin", ["1.5", "-0.1", "NaN"])
def test_invalid_margin_raises(margin):
    with pytest.raises(FinanceInputError):
        suggest_price(D("100"), margin)  # type: ignore[arg-type]


def test_negative_cost_raises():
    with pytest.raises(FinanceInputError):
        suggest_price(D("-1"), D("0.1"))


# --------------------------------------------------------------------- evaluation
def test_evaluates_profit_margin_and_markup_of_a_given_price():
    # cost 1733.08, price 2000: profit 266.92, margin 266.92/2000 = 0.13346 -> 0.1335,
    # markup 266.92/1733.08 = 0.15401 -> 0.1540
    r = calculate_bid_pricing(cost("1733.08"), D("2000"), D("0.10"))
    assert r.profit == D("266.92")
    assert r.margin_rate == D("0.1335") and r.markup_rate == D("0.1540")
    assert r.meets_target_margin is True and r.outcome == "meets_target"
    assert r.suggested_price == D("1925.65")  # 1733.08 / 0.9 = 1925.6444... rounded UP
    assert r.shortfall_to_suggested_price is None


def test_below_target_reports_shortfall_to_suggested_price():
    # cost 900, target 10% -> suggested 1000; bid 950 -> profit 50, margin 5.26%
    r = calculate_bid_pricing(cost("900"), D("950"), D("0.10"))
    assert r.outcome == "below_target" and r.meets_target_margin is False
    assert r.profit == D("50.00") and r.margin_rate == D("0.0526")
    assert r.shortfall_to_suggested_price == D("50.00")


def test_price_exactly_at_target_meets_target():
    r = calculate_bid_pricing(cost("900"), D("1000"), D("0.10"))
    assert r.meets_target_margin is True and r.outcome == "meets_target"


def test_just_below_target_does_not_meet_it_even_if_margin_rounds_up():
    # profit 99.99 on 999.99 -> 0.0999990 rounds to 0.1000 but does NOT meet 10%.
    r = calculate_bid_pricing(cost("900"), D("999.99"), D("0.10"))
    assert r.margin_rate == D("0.1000") and r.meets_target_margin is False
    assert r.outcome == "below_target"


def test_loss_and_zero_profit_outcomes():
    loss = calculate_bid_pricing(cost("1000"), D("800"), D("0.1"))
    assert loss.outcome == "loss" and loss.profit == D("-200.00") and loss.margin_rate == D("-0.2500")
    flat = calculate_bid_pricing(cost("1000"), D("1000"), D("0.1"))
    assert flat.outcome == "no_profit" and flat.profit == D("0.00") and flat.meets_target_margin is False


def test_unknown_target_margin_is_not_assumed_zero():
    r = calculate_bid_pricing(cost("1000"), D("1200"), None)
    assert r.outcome == "profit_target_unknown"
    assert r.meets_target_margin is None and r.suggested_price is None
    assert "target_margin_rate is unknown" in r.reasons


def test_no_bid_price_gives_only_the_suggestion():
    r = calculate_bid_pricing(cost("900"), None, D("0.1"))
    assert r.outcome == "no_bid_price" and r.suggested_price == D("1000.00")
    assert r.profit is None and r.margin_rate is None and r.meets_target_margin is None


def test_incomplete_costs_never_produce_profit_or_a_profitable_outcome():
    r = calculate_bid_pricing(incomplete(), D("1000000"), D("0.1"))
    assert r.outcome == "incomplete_costs"
    assert r.profit is None and r.margin_rate is None and r.markup_rate is None
    assert r.suggested_price is None and r.meets_target_margin is None
    assert any("incomplete" in x for x in r.reasons)


def test_incomplete_cost_with_no_price_and_no_margin():
    r = calculate_bid_pricing(calculate_cost_model([], None, None), None, None)
    assert r.outcome == "incomplete_costs" and r.suggested_price is None


# ----------------------------------------------------------------- degenerate values
def test_zero_bid_price_has_undefined_margin_not_a_crash():
    r = calculate_bid_pricing(cost("500"), D("0"), D("0.1"))
    assert r.margin_rate is None and r.profit == D("-500.00") and r.outcome == "loss"
    assert r.markup_rate == D("-1.0000")
    assert any("margin is undefined" in x for x in r.reasons)


def test_zero_cost_and_zero_price():
    r = calculate_bid_pricing(cost("0"), D("0"), D("0.1"))
    assert r.profit == D("0.00") and r.margin_rate is None and r.markup_rate is None
    assert r.outcome == "no_profit"


def test_zero_cost_positive_price_has_no_markup():
    r = calculate_bid_pricing(cost("0"), D("100"), D("0.1"))
    assert r.markup_rate is None and r.margin_rate == D("1.0000") and r.outcome == "meets_target"


def test_hundred_percent_target_margin_cannot_be_priced():
    r = calculate_bid_pricing(cost("100"), D("500"), D("1"))
    assert r.suggested_price is None and r.meets_target_margin is False
    assert "a target margin of 100% cannot be priced" in r.reasons


def test_negative_bid_price_raises():
    with pytest.raises(FinanceInputError):
        calculate_bid_pricing(cost("100"), D("-5"), D("0.1"))


def test_price_includes_contingency_and_overhead_from_the_cost_model():
    # direct 1000, cont 10% = 100, ovh 5% of 1100 = 55 -> total 1155 ; /0.9 = 1283.333 -> 1283.34
    r = calculate_bid_pricing(cost("1000", "0.10", "0.05"), None, D("0.10"))
    assert r.total_cost == D("1155.00") and r.suggested_price == D("1283.34")


def test_deterministic_and_json_safe():
    a = calculate_bid_pricing(cost("1733.08"), D("2000"), D("0.1"))
    assert a == calculate_bid_pricing(cost("1733.08"), D("2000"), D("0.1"))
    out = json.loads(json.dumps(a.as_dict()))
    assert out["profit"] == "266.92" and out["margin_rate"] == "0.1335" and out["outcome"] == "meets_target"
    unknown = json.loads(json.dumps(calculate_bid_pricing(incomplete(), D("1"), D("0.1")).as_dict()))
    assert unknown["profit"] is None and unknown["total_cost"] is None
