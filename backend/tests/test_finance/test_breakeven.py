"""Tests for break-even. Reference case worked by hand:

fixed direct 1000, variable direct 2000, contingency 10%, overhead 5%
  fixed    = 1000 + 100 + 55   = 1155        variable = 2000 * 1.155 = 2310        total = 3465
"""
import json
from decimal import Decimal as D

import pytest

from app.services.finance.breakeven import calculate_break_even
from app.services.finance.cost_model import CostLine, FinanceInputError, calculate_cost_model


def mk(i, unit, behavior, qty="1"):
    return CostLine(i, f"l{i}", "labour", D(qty), None if unit is None else D(unit), behavior, "Verified")


def ref_cost(cont="0.10", ovh="0.05"):
    return calculate_cost_model([mk(1, "1000", "fixed"), mk(2, "2000", "variable")], cont, ovh)


def test_reference_break_even():
    cost = ref_cost()
    assert (cost.fixed_cost, cost.variable_cost, cost.total_cost) == (D("1155.00"), D("2310.00"), D("3465.00"))
    r = calculate_break_even(cost, D("5000"))
    # contribution 5000 - 2310 = 2690 ; ratio 2690/5000 = 0.5380
    # progress 1155/2690 = 0.42936 -> 0.4294 ; revenue 0.429368... * 5000 = 2146.84
    assert r.status == "ok" and r.reached_within_contract is True
    assert r.contribution == D("2690.00") and r.contribution_margin_ratio == D("0.5380")
    assert r.break_even_progress == D("0.4294") and r.break_even_revenue == D("2146.84")
    assert r.margin_of_safety == D("0.5706")
    assert r.profit_at_full_delivery == D("1535.00")  # 5000 - 3465
    assert r.reasons == ()


def test_profit_at_break_even_revenue_is_zero_within_a_cent():
    cost, price = ref_cost(), D("5000")
    r = calculate_break_even(cost, price)
    progress = r.break_even_revenue / price
    profit = price * progress - cost.fixed_cost - cost.variable_cost * progress
    assert abs(profit) < D("0.01")


def test_price_equal_to_total_cost_breaks_even_at_full_delivery():
    r = calculate_break_even(ref_cost(), D("3465"))
    assert r.status == "ok" and r.break_even_progress == D("1.0000")
    assert r.break_even_revenue == D("3465.00") and r.profit_at_full_delivery == D("0.00")
    assert r.margin_of_safety == D("0.0000")


def test_price_between_variable_and_total_cost_never_breaks_even_within_contract():
    # P 3000 > V 2310 but < total 3465: progress 1155/690 = 1.6739 (> 1) -> loses money as priced
    r = calculate_break_even(ref_cost(), D("3000"))
    assert r.status == "not_reached_within_contract" and r.reached_within_contract is False
    assert r.break_even_progress == D("1.6739") and r.break_even_revenue == D("5021.74")
    assert r.margin_of_safety == D("-0.6739")
    assert r.profit_at_full_delivery == D("-465.00")
    assert any("loses money" in x for x in r.reasons)


@pytest.mark.parametrize("price", ["2310", "2000", "1"])
def test_price_not_above_variable_cost_has_no_break_even(price):
    r = calculate_break_even(ref_cost(), D(price))
    assert r.status == "no_break_even"
    assert r.break_even_revenue is None and r.break_even_progress is None
    assert r.contribution == D(price) - D("2310.00")  # reported, can be negative
    assert r.profit_at_full_delivery == D(price) - D("3465.00")


def test_all_variable_costs_break_even_at_zero_revenue():
    cost = calculate_cost_model([mk(1, "1000", "variable")], "0", "0")
    r = calculate_break_even(cost, D("1500"))
    assert r.status == "ok" and r.break_even_revenue == D("0.00") and r.break_even_progress == D("0.0000")
    assert r.margin_of_safety == D("1.0000")


def test_all_fixed_costs_break_even_when_price_covers_them():
    cost = calculate_cost_model([mk(1, "1000", "fixed")], "0", "0")
    r = calculate_break_even(cost, D("4000"))  # contribution = price, progress = 1000/4000
    assert r.break_even_progress == D("0.2500") and r.break_even_revenue == D("1000.00")
    assert r.contribution_margin_ratio == D("1.0000")


# ------------------------------------------------------- missing data / safe failure
def test_incomplete_costs_give_no_figures():
    cost = calculate_cost_model([mk(1, "1000", "fixed"), mk(2, None, "variable")], "0", "0")
    r = calculate_break_even(cost, D("5000"))
    assert r.status == "incomplete_costs"
    assert r.break_even_revenue is None and r.profit_at_full_delivery is None
    assert any("incomplete" in x for x in r.reasons)


def test_unknown_rates_give_no_figures():
    r = calculate_break_even(ref_cost(cont=None), D("5000"))
    assert r.status == "incomplete_costs" and r.break_even_revenue is None


def test_unclassified_lines_are_listed_and_not_guessed():
    cost = calculate_cost_model([mk(1, "1000", "fixed"), mk(2, "500", None)], "0", "0")
    r = calculate_break_even(cost, D("5000"))
    assert r.status == "unclassified_costs" and r.break_even_revenue is None
    assert [x["id"] for x in r.unclassified_lines] == [2]


def test_missing_price_and_zero_price():
    none = calculate_break_even(ref_cost(), None)
    assert none.status == "no_bid_price" and none.break_even_revenue is None
    zero = calculate_break_even(ref_cost(), D("0"))  # would be division by zero
    assert zero.status == "zero_bid_price" and zero.contribution_margin_ratio is None


def test_every_blocking_cause_is_listed_with_first_cause_as_status():
    cost = calculate_cost_model([mk(1, None, None)], "0", "0")
    r = calculate_break_even(cost, None)
    assert r.status == "incomplete_costs"
    assert any("bid_price" in x for x in r.reasons) and any("incomplete" in x for x in r.reasons)


def test_empty_cost_model_is_not_a_zero_cost_break_even():
    r = calculate_break_even(calculate_cost_model([], "0", "0"), D("1000"))
    assert r.status == "incomplete_costs" and r.break_even_revenue is None


def test_zero_total_cost_is_handled():
    cost = calculate_cost_model([mk(1, "0", "fixed"), mk(2, "0", "variable")], "0", "0")
    r = calculate_break_even(cost, D("100"))
    assert r.status == "ok" and r.break_even_revenue == D("0.00") and r.profit_at_full_delivery == D("100.00")


def test_invalid_price_raises():
    with pytest.raises(FinanceInputError):
        calculate_break_even(ref_cost(), D("-1"))
    with pytest.raises(FinanceInputError):
        calculate_break_even(ref_cost(), "abc")  # type: ignore[arg-type]


def test_deterministic_and_json_safe():
    a, b = calculate_break_even(ref_cost(), D("5000")), calculate_break_even(ref_cost(), D("5000"))
    assert a == b
    out = json.loads(json.dumps(a.as_dict()))
    assert out["break_even_revenue"] == "2146.84" and out["status"] == "ok"
    blocked = json.loads(json.dumps(calculate_break_even(ref_cost(), None).as_dict()))
    assert blocked["break_even_revenue"] is None and blocked["status"] == "no_bid_price"
