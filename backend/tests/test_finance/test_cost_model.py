"""Tests for the cost build-up (cost_model.py). Expected numbers are worked out by hand in the
comments, not produced by calling the code under test."""
import json
from decimal import Decimal as D

import pytest

from app.models import Company, CostBehavior, CostCategory, FinancialCostItem, FinancialModel, Project
from app.models.enums import VerificationStatus
from app.services.finance.cost_model import (
    CostLine,
    FinanceInputError,
    FinancialInputs,
    calculate_cost_model,
    inputs_from_model,
    round_money,
)


def line(i=1, cat="labour", qty="1", unit="100", behavior="variable", status="Verified", **kw):
    return CostLine(
        id=i, description=f"line {i}", category=cat, quantity=D(qty),
        unit_cost=None if unit is None else D(unit), cost_behavior=behavior,
        verification_status=status, **kw,
    )


def calc(lines, cont="0", ovh="0"):
    return calculate_cost_model(lines, cont, ovh)  # raw values: the engine validates them


# ------------------------------------------------------------------ normal cases
def test_build_up_with_half_up_rounding():
    # direct = 10 x 100.00 + 2 x 250.25 = 1500.50
    # contingency 5%  = 75.025  -> 75.03 (half up)
    # overhead 10% of (1500.50 + 75.03) = 157.553 -> 157.55
    # total = 1500.50 + 75.03 + 157.55 = 1733.08
    r = calc([line(1, "labour", "10", "100.00"), line(2, "materials", "2", "250.25")], "0.05", "0.10")
    assert r.complete and r.incomplete_reasons == ()
    assert r.direct_cost == D("1500.50")
    assert r.contingency == D("75.03")
    assert r.overhead == D("157.55")
    assert r.total_cost == D("1733.08")
    assert r.total_cost == r.direct_cost + r.contingency + r.overhead


def test_line_total_is_rounded_half_up_per_line():
    # 3 x 0.335 = 1.005 -> 1.01 ; the line is rounded before it is summed.
    r = calc([line(1, qty="3", unit="0.335"), line(2, qty="3", unit="0.335")])
    assert r.direct_cost == D("2.02")


def test_fractional_quantities_and_zero_rates_are_explicit_zero():
    r = calc([line(qty="2.5", unit="40")], "0", "0")  # 2.5 x 40 = 100
    assert r.complete and r.total_cost == D("100.00") and r.contingency == D("0.00")


def test_decimal_math_has_no_binary_float_error():
    # 0.1 + 0.2 style errors must not appear; floats are read through str().
    lines = [line(1, unit=0.1, qty="3"), line(2, unit=0.2, qty="1")]
    assert calc(lines).direct_cost == D("0.50")


def test_zero_unit_cost_is_a_known_zero_not_unknown():
    r = calc([line(1, unit="0"), line(2, unit="10")])
    assert r.complete and r.total_cost == D("10.00") and r.unknown_lines == ()


def test_by_category_and_categories_without_lines():
    r = calc([line(1, "labour", unit="100"), line(2, "labour", unit="50"), line(3, "materials", unit="10")])
    assert r.by_category["labour"] == {"known_subtotal": "150.00", "line_count": 2, "unknown_line_count": 0}
    assert r.by_category["materials"]["known_subtotal"] == "10.00"
    assert "equipment" in r.categories_without_lines and "labour" not in r.categories_without_lines
    assert r.complete  # a missing category is informational, it does not block the total


def test_site_overhead_is_direct_and_not_double_counted():
    # site_overhead line is part of direct cost; overhead_rate applies once on top.
    r = calc([line(1, "site_overhead", unit="1000")], "0", "0.10")
    assert r.direct_cost == D("1000.00") and r.overhead == D("100.00") and r.total_cost == D("1100.00")


# ------------------------------------------------------------- fixed / variable split
def test_fixed_variable_split_includes_pro_rata_markups():
    # fixed 1000 -> cont 10% 100, ovh 5% of 1100 = 55 -> 1155
    # all   3000 -> cont 300,     ovh 5% of 3300 = 165 -> 3465 ; variable = 3465 - 1155 = 2310
    r = calc([line(1, unit="1000", behavior="fixed"), line(2, unit="2000", behavior="variable")], "0.10", "0.05")
    assert r.total_cost == D("3465.00")
    assert r.fixed_cost == D("1155.00") and r.variable_cost == D("2310.00")


@pytest.mark.parametrize("cont,ovh", [("0.033", "0.071"), ("0.5", "0.5"), ("1", "1"), ("0.0001", "0.9999")])
def test_fixed_plus_variable_always_equals_total_exactly(cont, ovh):
    lines = [line(1, unit="333.33", qty="3", behavior="fixed"), line(2, unit="0.01", behavior="variable"),
             line(3, unit="7777.77", qty="1.5", behavior="variable")]
    r = calc(lines, cont, ovh)
    assert r.fixed_cost + r.variable_cost == r.total_cost
    assert r.variable_cost >= 0 and r.fixed_cost >= 0


def test_unclassified_lines_block_the_split_and_are_listed():
    r = calc([line(1, unit="100", behavior="fixed"), line(2, unit="50", behavior=None)])
    assert r.total_cost == D("150.00")  # total is still known
    assert r.fixed_cost is None and r.variable_cost is None
    assert [x["id"] for x in r.unclassified_lines] == [2]


# ---------------------------------------------------------------- missing / unknown data
def test_unknown_unit_cost_is_never_zero():
    r = calc([line(1, unit="100"), line(2, unit=None)], "0.1", "0.1")
    assert not r.complete
    assert r.direct_cost is None and r.total_cost is None and r.contingency is None
    assert r.known_direct_subtotal == D("100.00")
    assert [x["id"] for x in r.unknown_lines] == [2]
    assert any("unknown unit cost" in x for x in r.incomplete_reasons)
    assert r.by_category["labour"]["unknown_line_count"] == 1


@pytest.mark.parametrize("cont,ovh,expected", [(None, "0.1", "contingency_rate"), ("0.1", None, "overhead_rate")])
def test_unknown_rate_is_never_zero(cont, ovh, expected):
    r = calc([line(unit="100")], cont, ovh)
    assert not r.complete and r.total_cost is None
    assert any(expected in x for x in r.incomplete_reasons)


def test_no_cost_lines_is_incomplete_not_zero_cost():
    r = calc([], "0.1", "0.1")
    assert not r.complete and r.total_cost is None and r.direct_cost is None
    assert r.incomplete_reasons == ("no cost lines",)
    assert r.known_direct_subtotal == D("0")


def test_all_problems_are_reported_together():
    r = calc([line(unit=None)], None, None)
    assert len(r.incomplete_reasons) == 3


def test_rejected_lines_are_excluded_and_counted():
    r = calc([line(1, unit="100"), line(2, unit="999", status="Rejected"), line(3, unit=None, status="Rejected")])
    assert r.complete and r.total_cost == D("100.00")  # a rejected unknown line does not block
    assert r.line_count == 1 and r.rejected_line_count == 2


def test_lines_needing_review_are_included_but_flagged():
    r = calc([line(1, unit="100", status="Requires review"), line(2, unit="10", status="Conflicting"),
              line(3, unit="1", status="Estimated"), line(4, unit="1", status="Assumption")])
    assert r.total_cost == D("112.00")
    assert sorted(x["id"] for x in r.needs_review_lines) == [1, 2]


# ----------------------------------------------------------------------- invalid input
@pytest.mark.parametrize(
    "kwargs",
    [
        dict(qty="-1"),
        dict(unit="-0.01"),
        dict(cat="nonsense"),
        dict(behavior="semi"),
        dict(start_month=3, end_month=2),
        dict(start_month=-1),
    ],
)
def test_invalid_lines_raise(kwargs):
    with pytest.raises(FinanceInputError):
        line(**kwargs)


@pytest.mark.parametrize("bad", ["1.01", "-0.01", "NaN", "abc", "Infinity"])
def test_invalid_rates_raise(bad):
    with pytest.raises(FinanceInputError):
        calc([line()], bad, "0")
    with pytest.raises(FinanceInputError):
        calc([line()], "0", bad)


def test_boolean_and_wrong_types_rejected():
    with pytest.raises(FinanceInputError):
        calculate_cost_model([line()], True, D("0"))
    with pytest.raises(FinanceInputError):
        CostLine(1, "x", "labour", D("1"), [1], None)  # type: ignore[arg-type]


def test_financial_inputs_validation():
    with pytest.raises(FinanceInputError):
        FinancialInputs(advance_payment_rate=D("0.6"), retention_rate=D("0.5"))
    with pytest.raises(FinanceInputError):
        FinancialInputs(duration_months=0)
    with pytest.raises(FinanceInputError):
        FinancialInputs(duration_months=2.5)  # type: ignore[arg-type]
    with pytest.raises(FinanceInputError):
        FinancialInputs(payment_terms_days=-1)
    with pytest.raises(FinanceInputError):
        FinancialInputs(bid_price=D("-1"))
    FinancialInputs(advance_payment_rate=D("0.5"), retention_rate=D("0.5"))  # exactly 1 is allowed


# ------------------------------------------------------------------ robustness
def test_very_large_values_do_not_overflow_or_lose_precision():
    r = calc([line(qty="99999999999.999", unit="999999999999.99")], "0.5", "0.5")
    assert r.direct_cost == round_money(D("99999999999.999") * D("999999999999.99"))
    assert r.total_cost == r.direct_cost + r.contingency + r.overhead


def test_deterministic_and_json_safe():
    lines = [line(1, unit="12.34", qty="3"), line(2, unit=None), line(3, "equipment", unit="5")]
    a, b = calc(lines, "0.07", "0.03"), calc(lines, "0.07", "0.03")
    assert a == b and a.as_dict() == b.as_dict()
    text = json.dumps(a.as_dict())
    assert '"total_cost": null' in text  # unknown stays null, never "0.00"


# ------------------------------------------------------------------ ORM adapter
def _model(session, **kw):
    company = Company(name="Acme")
    session.add(company)
    session.flush()
    project = Project(company_id=company.id, name="P")
    session.add(project)
    session.flush()
    model = FinancialModel(project_id=project.id, **kw)
    session.add(model)
    session.flush()
    return model


def test_inputs_from_model_reads_orm_objects(session):
    model = _model(session, currency="eur", bid_price="5000", duration_months=6, payment_terms_days=45,
                   advance_payment_rate="0.1", retention_rate="0.05", contingency_rate="0.05",
                   overhead_rate="0.08", target_margin_rate="0.1")
    session.add_all([
        FinancialCostItem(financial_model_id=model.id, description="Crew", category=CostCategory.LABOUR,
                          cost_behavior=CostBehavior.VARIABLE, quantity="2.5", unit_cost="100",
                          start_month=0, end_month=2),
        FinancialCostItem(financial_model_id=model.id, description="Crane", category=CostCategory.EQUIPMENT,
                          quantity=1, unit_cost=None),
    ])
    session.flush()
    session.refresh(model)
    inputs = inputs_from_model(model)
    assert inputs.currency == "EUR" and inputs.bid_price == D("5000.00") and inputs.duration_months == 6
    assert inputs.target_margin_rate == D("0.1000")
    crew, crane = inputs.lines
    assert crew.category == "labour" and crew.cost_behavior == "variable" and crew.total == D("250.00")
    assert crane.unit_cost is None and crane.cost_behavior is None  # unknown stays unknown
    assert crane.verification_status == VerificationStatus.REQUIRES_REVIEW.value
    assert not calculate_cost_model(inputs.lines, inputs.contingency_rate, inputs.overhead_rate).complete
