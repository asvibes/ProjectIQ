"""Tests for cash flow and the end-to-end pipeline. Small cases are worked by hand in comments."""
import json
from decimal import Decimal as D

import pytest

from app.models import Company, FinancialCostItem, FinancialModel, Project, Scenario
from app.models.types import utcnow
from app.services.finance.cashflow import (
    allocate_cents,
    calculate_cash_flow,
    calculate_financial_results,
    payment_lag_months,
)
from app.services.finance.cost_model import (
    ENGINE_VERSION,
    CostLine,
    FinanceInputError,
    FinancialInputs,
    calculate_cost_model,
    inputs_from_model,
)
from app.services.scenario_compare import compare_stored


def mk(i, unit, qty="1", start=None, end=None, cat="labour", behavior="variable", status="Verified"):
    return CostLine(i, f"l{i}", cat, D(qty), None if unit is None else D(unit), behavior, status, start, end)


def cf(lines, **kw):
    args = dict(bid_price=D("12000"), duration_months=3, payment_terms_days=30, advance_payment_rate=D("0.10"),
                retention_rate=D("0.05"), contingency_rate=D("0"), overhead_rate=D("0"))
    args.update(kw)
    return calculate_cash_flow(lines, **args)


def col(r, key):
    return [D(m[key]) for m in r.months]


# ---------------------------------------------------------------------- allocation
def test_allocate_sums_exactly_and_is_never_negative():
    parts = allocate_cents(D("100.00"), [1, 1, 1])
    assert parts == [D("33.33"), D("33.33"), D("33.34")] and sum(parts) == D("100.00")
    small = allocate_cents(D("0.04"), [1] * 6)
    assert sum(small) == D("0.04") and min(small) >= 0  # round-each-then-fix would give a negative month


def test_allocate_is_proportional_and_deterministic():
    assert allocate_cents(D("10.00"), [1, 3]) == [D("2.50"), D("7.50")]
    assert allocate_cents(D("10.00"), [0, 5, 0]) == [D("0.00"), D("10.00"), D("0.00")]
    assert allocate_cents(D("7.77"), [3, 5, 9]) == allocate_cents(D("7.77"), [3, 5, 9])


def test_allocate_edge_cases():
    assert allocate_cents(D("0"), []) == []
    assert allocate_cents(D("0"), [0, 0]) == [D("0.00"), D("0.00")]
    with pytest.raises(ValueError):
        allocate_cents(D("1"), [])
    with pytest.raises(ValueError):
        allocate_cents(D("1"), [0, 0])
    with pytest.raises(ValueError):
        allocate_cents(D("-1"), [1])
    with pytest.raises(ValueError):
        allocate_cents(D("1"), [-1, 2])


@pytest.mark.parametrize("days,lag", [(0, 0), (1, 1), (29, 1), (30, 1), (31, 2), (45, 2), (60, 2), (61, 3), (90, 3)])
def test_payment_lag_is_ceiling_of_30_day_months(days, lag):
    assert payment_lag_months(days) == lag


# ------------------------------------------------------------------- hand-worked cases
def test_hand_worked_case_with_advance_retention_and_lag():
    # price 12000, 3 months, terms 30d (lag 1), advance 10% = 1200, retention 5% = 600.
    # cost 3000 spread over months 0-2 -> 1000/month.
    # invoices 4000 each; retention 200 each; after retention 3800; advance recovery 400 each;
    # net 3400 each, received in months 1,2,3. Advance 1200 in month 0. Retention 600 in month D+lag = 4.
    r = cf([mk(1, "3000", start=0, end=2)])
    assert r.status == "ok" and r.complete and r.payment_lag_months == 1
    assert r.advance_amount == D("1200.00") and r.retention_amount == D("600.00")
    assert col(r, "costs") == [D(1000), D(1000), D(1000), D(0), D(0)]
    assert col(r, "receipts") == [D(1200), D(3400), D(3400), D(3400), D(600)]
    assert col(r, "cumulative") == [D(200), D(2600), D(5000), D(8400), D(9000)]
    assert r.closing_balance == D("9000.00") == D("12000") - D("3000")
    assert r.total_receipts == D("12000.00") and r.total_costs_scheduled == D("3000.00")
    assert r.cumulative_low_point == D("200.00")
    assert r.peak_funding_requirement == D("0.00") and r.peak_funding_month is None


def test_upfront_cost_and_slow_payment_create_a_funding_requirement():
    # No advance/retention, terms 60d (lag 2). Cost 6000 in month 0 only. Invoices 4000 in months 2,3,4.
    # cumulative: -6000, -6000, -2000, 2000, 6000 ; low point -6000 first reached in month 0.
    r = cf([mk(1, "6000", start=0, end=0)], advance_payment_rate=D("0"), retention_rate=D("0"),
           payment_terms_days=60)
    assert col(r, "cumulative") == [D(-6000), D(-6000), D(-2000), D(2000), D(6000)]
    assert r.peak_funding_requirement == D("6000.00") and r.peak_funding_month == 0
    assert r.closing_balance == D("6000.00")


def test_zero_payment_terms_means_no_delay_and_zero_rates_are_explicit():
    r = cf([mk(1, "3000", start=0, end=2)], payment_terms_days=0, advance_payment_rate=D("0"), retention_rate=D("0"))
    assert r.payment_lag_months == 0
    assert col(r, "receipts") == [D(4000), D(4000), D(4000)]  # received in the month billed, no retention release month


def test_retention_only_released_after_the_final_invoice_falls_due():
    r = cf([mk(1, "100", start=0, end=0)], advance_payment_rate=D("0"), retention_rate=D("0.10"),
           payment_terms_days=0, duration_months=2, bid_price=D("1000"))
    # invoices 500 each, 50 retained each, net 450 in months 0,1; 100 released in month D + lag = 2
    assert col(r, "receipts") == [D(450), D(450), D(100)]


def test_costs_beyond_the_duration_extend_the_series_and_warn():
    r = cf([mk(1, "300", start=2, end=5)], duration_months=3, payment_terms_days=0,
           advance_payment_rate=D("0"), retention_rate=D("0"))
    assert len(r.months) == 6 and r.warnings and "beyond duration_months" in r.warnings[0]
    assert r.total_costs_scheduled == D("300.00")


def test_contingency_and_overhead_are_spread_and_sum_exactly_to_the_cost_model_total():
    lines = [mk(1, "1000.01", start=0, end=2), mk(2, "333.33", qty="3", start=1, end=1), mk(3, "7.77", start=3, end=6)]
    r = cf(lines, contingency_rate=D("0.0725"), overhead_rate=D("0.0333"))
    model_total = calculate_cost_model(lines, D("0.0725"), D("0.0333")).total_cost
    assert r.complete and r.total_costs_scheduled == model_total
    assert sum(col(r, "costs")) == model_total and min(col(r, "costs")) >= 0
    assert r.closing_balance == D("12000") - model_total


def test_single_month_line_and_overlapping_lines_add_up():
    r = cf([mk(1, "100", start=1, end=1), mk(2, "200", start=1, end=2)], advance_payment_rate=D("0"),
           retention_rate=D("0"))
    assert col(r, "costs")[:3] == [D(0), D(200), D(100)]  # month1: 100 + 100 ; month2: 100


# ------------------------------------------------------------ invariants over a grid
@pytest.mark.parametrize("price", ["100.01", "12345.67", "0.03", "999999.99"])
@pytest.mark.parametrize("duration", [1, 3, 7, 12])
@pytest.mark.parametrize("adv,ret", [("0", "0"), ("0.1", "0.05"), ("0.5", "0.5"), ("0.3333", "0.6667"), ("1", "0"), ("0", "1")])
@pytest.mark.parametrize("terms", [0, 45, 90])
def test_receipts_always_equal_price_and_no_receipt_is_negative(price, duration, adv, ret, terms):
    lines = [mk(1, "1234.56", start=0, end=duration - 1)]
    r = cf(lines, bid_price=D(price), duration_months=duration, advance_payment_rate=D(adv),
           retention_rate=D(ret), payment_terms_days=terms)
    assert r.total_receipts == D(price)
    assert min(col(r, "receipts")) >= 0
    assert r.closing_balance == D(price) - D("1234.56")
    assert r.advance_amount + r.retention_amount <= D(price)
    assert D(r.months[-1]["cumulative"]) == r.closing_balance


def test_zero_price_has_no_receipts_and_no_division_errors():
    r = cf([mk(1, "500", start=0, end=1)], bid_price=D("0"))
    assert r.status == "ok" and r.total_receipts == D("0.00")
    assert r.closing_balance == D("-500.00") and r.peak_funding_requirement == D("500.00")


# ---------------------------------------------------- missing data: never silently zero
@pytest.mark.parametrize(
    "name",
    ["bid_price", "duration_months", "payment_terms_days", "advance_payment_rate", "retention_rate",
     "contingency_rate", "overhead_rate"],
)
def test_each_unknown_input_blocks_the_calculation_and_is_named(name):
    r = cf([mk(1, "100", start=0, end=0)], **{name: None})
    assert r.status == "insufficient_inputs" and not r.complete
    assert r.missing_inputs == (name,)
    assert r.months == () and r.closing_balance is None and r.peak_funding_requirement is None


def test_unknown_payment_terms_are_not_treated_as_immediate_payment():
    unknown = cf([mk(1, "100", start=0, end=0)], payment_terms_days=None)
    zero = cf([mk(1, "100", start=0, end=0)], payment_terms_days=0)
    assert unknown.months == () and len(zero.months) > 0


def test_several_missing_inputs_are_all_listed():
    r = cf([], bid_price=None, duration_months=None, retention_rate=None)
    assert r.missing_inputs == ("bid_price", "duration_months", "retention_rate")


def test_unknown_cost_makes_result_partial_and_withholds_headline_metrics():
    r = cf([mk(1, "3000", start=0, end=2), mk(2, None, start=0, end=0)])
    assert r.status == "partial" and not r.complete
    assert [x["id"] for x in r.unknown_lines] == [2]
    assert r.months  # the known part is shown...
    assert r.closing_balance is None and r.cumulative_low_point is None  # ...but not summarised as if final
    assert r.peak_funding_requirement is None and r.peak_funding_month is None


def test_unscheduled_lines_are_excluded_listed_and_not_spread():
    r = cf([mk(1, "3000", start=0, end=2), mk(2, "900"), mk(3, "900", start=1)])  # no timing / end missing
    assert r.status == "partial"
    assert sorted(x["id"] for x in r.unscheduled_lines) == [2, 3]
    assert r.total_costs_scheduled == D("3000.00")  # the 1800 is not hidden inside the months
    assert r.closing_balance is None


def test_no_cost_lines_is_partial_not_free():
    r = cf([])
    assert r.status == "partial" and r.incomplete_reasons == ("no cost lines",) and r.closing_balance is None


def test_rejected_lines_are_ignored():
    r = cf([mk(1, "3000", start=0, end=2), mk(2, None, status="Rejected"), mk(3, "999", status="Rejected")])
    assert r.status == "ok" and r.total_costs_scheduled == D("3000.00")


def test_performance_guarantee_is_exposure_only():
    r = cf([mk(1, "3000", start=0, end=2)], performance_guarantee_rate=D("0.10"))
    assert r.performance_guarantee_amount == D("1200.00")
    assert r.total_receipts == D("12000.00") and r.closing_balance == D("9000.00")  # no fee, no cash movement


# ----------------------------------------------------------------------- invalid input
@pytest.mark.parametrize(
    "kw",
    [
        dict(duration_months=0),
        dict(duration_months=2.5),
        dict(duration_months=True),
        dict(duration_months=1201),
        dict(payment_terms_days=-1),
        dict(bid_price=D("-1")),
        dict(advance_payment_rate=D("1.01")),
        dict(retention_rate=D("-0.1")),
        dict(contingency_rate=D("2")),
        dict(advance_payment_rate=D("0.6"), retention_rate=D("0.5")),
    ],
)
def test_invalid_inputs_raise(kw):
    with pytest.raises(FinanceInputError):
        cf([mk(1, "100", start=0, end=0)], **kw)


def test_deterministic_and_json_safe():
    lines = [mk(1, "1234.56", start=0, end=3), mk(2, None)]
    a, b = cf(lines), cf(lines)
    assert a == b
    out = json.loads(json.dumps(a.as_dict()))
    assert out["status"] == "partial" and out["closing_balance"] is None


# ============================================================================ pipeline
def pipeline_inputs(**overrides):
    base = dict(
        lines=[
            mk(1, "1000.50", qty="10", start=0, end=5, cat="labour", behavior="variable"),
            mk(2, "50000", start=0, end=0, cat="equipment", behavior="fixed"),
            mk(3, "250", qty="100", start=1, end=4, cat="materials", behavior="variable"),
        ],
        currency="USD", bid_price=D("140000"), duration_months=6, payment_terms_days=45,
        advance_payment_rate=D("0.1"), retention_rate=D("0.05"), contingency_rate=D("0.05"),
        overhead_rate=D("0.08"), target_margin_rate=D("0.1"),
    )
    base.update(overrides)
    return FinancialInputs(**base)


def test_pipeline_hand_checked_figures():
    # direct 10005 + 50000 + 25000 = 85005.00 ; contingency 5% = 4250.25 ;
    # overhead 8% of 89255.25 = 7140.42 ; total 96395.67 ; suggested = 96395.67 / 0.9 = 107106.30
    # profit at 140000 = 43604.33 ; margin 0.3115
    # fixed 50000 -> cont 2500, ovh 4200 -> 56700 ; variable 39695.67 ;
    # break-even progress 56700 / (140000 - 39695.67) = 0.5653 ; revenue 79139.16
    r = calculate_financial_results(pipeline_inputs())
    assert r["engine_version"] == ENGINE_VERSION and r["price_basis"] == "bid_price" and r["costs_complete"] is True
    assert (r["direct_cost"], r["total_cost"]) == ("85005.00", "96395.67")
    assert r["suggested_price"] == "107106.30" and r["profit"] == "43604.33" and r["margin_rate"] == "0.3115"
    assert r["pricing_outcome"] == "meets_target"
    assert r["break_even_status"] == "ok"
    assert (r["break_even_progress"], r["break_even_revenue"]) == ("0.5653", "79139.16")
    assert r["cash_flow_status"] == "ok" and r["closing_balance"] == r["profit"] == "43604.33"
    assert D(r["peak_funding_requirement"]) > 0 and r["peak_funding_month"] == 1
    assert r["cost_model"]["total_cost"] == r["total_cost"]
    assert r["cash_flow"]["total_costs_scheduled"] == r["total_cost"]


def test_pipeline_uses_suggested_price_when_no_bid_price_and_says_so():
    r = calculate_financial_results(pipeline_inputs(bid_price=None))
    assert r["price_basis"] == "suggested_price" and r["bid_price"] is None
    assert r["suggested_price"] == "107106.30"
    assert r["break_even_status"] == "ok" and r["cash_flow"]["bid_price"] == "107106.30"
    assert r["pricing_outcome"] == "no_bid_price" and r["profit"] is None  # no profit claimed for a price nobody set


def test_pipeline_never_reports_an_incomplete_project_as_profitable():
    lines = list(pipeline_inputs().lines) + [mk(9, None, cat="logistics", start=2, end=3)]
    r = calculate_financial_results(pipeline_inputs(lines=lines))
    assert r["costs_complete"] is False and r["total_cost"] is None and r["direct_cost"] is None
    assert r["known_direct_subtotal"] == "85005.00"
    assert r["profit"] is None and r["margin_rate"] is None and r["pricing_outcome"] == "incomplete_costs"
    assert r["break_even_status"] == "incomplete_costs" and r["break_even_revenue"] is None
    assert r["cash_flow_status"] == "partial" and r["closing_balance"] is None
    assert r["suggested_price"] is None


def test_pipeline_with_nothing_known_returns_unknowns_not_zeros():
    r = calculate_financial_results(FinancialInputs())
    assert r["costs_complete"] is False and r["price_basis"] == "none"
    for key in ("total_cost", "profit", "break_even_revenue", "peak_funding_requirement", "closing_balance", "suggested_price"):
        assert r[key] is None, key
    assert r["cash_flow_status"] == "insufficient_inputs" and r["pricing_outcome"] == "incomplete_costs"


def test_pipeline_loss_making_price():
    r = calculate_financial_results(pipeline_inputs(bid_price=D("90000")))
    assert r["pricing_outcome"] == "loss" and r["profit"] == "-6395.67"
    assert r["break_even_status"] == "not_reached_within_contract"
    assert r["closing_balance"] == "-6395.67"


def test_pipeline_is_deterministic():
    a, b = calculate_financial_results(pipeline_inputs()), calculate_financial_results(pipeline_inputs())
    assert a == b and json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_results_are_json_safe_with_decimals_as_strings():
    r = calculate_financial_results(pipeline_inputs())
    assert json.loads(json.dumps(r)) == r
    scalars = [v for v in r.values() if not isinstance(v, dict)]
    assert all(v is None or isinstance(v, (bool, int, str)) for v in scalars)  # what scenario_compare reads
    assert isinstance(r["total_cost"], str) and isinstance(r["cash_flow"]["months"][0]["costs"], str)


# ---------------------------------------------- stored in FinancialModel / scenario compare
def _persisted_model(session):
    company = Company(name="Acme")
    session.add(company)
    session.flush()
    project = Project(company_id=company.id, name="Plant")
    session.add(project)
    session.flush()
    model = FinancialModel(
        project_id=project.id, bid_price="140000", duration_months=6, payment_terms_days=45,
        advance_payment_rate="0.1", retention_rate="0.05", contingency_rate="0.05", overhead_rate="0.08",
        target_margin_rate="0.1",
    )
    session.add(model)
    session.flush()
    for i, (cat, behavior, qty, unit, s, e) in enumerate(
        [("labour", "variable", "10", "1000.50", 0, 5), ("equipment", "fixed", "1", "50000", 0, 0),
         ("materials", "variable", "100", "250", 1, 4)]
    ):
        session.add(FinancialCostItem(financial_model_id=model.id, category=cat, cost_behavior=behavior,
                                      description=f"item {i}", quantity=qty, unit_cost=unit, start_month=s, end_month=e))
    session.flush()
    session.refresh(model)
    return project, model


def test_results_round_trip_through_financial_model_and_scenario_compare(session):
    project, model = _persisted_model(session)
    results = calculate_financial_results(inputs_from_model(model))
    assert results["total_cost"] == "96395.67" and results["break_even_revenue"] == "79139.16"

    model.results, model.calculated_at, model.engine_version = results, utcnow(), results["engine_version"]
    session.flush()
    session.expire_all()
    assert model.results["profit"] == "43604.33" and model.engine_version == ENGINE_VERSION

    # A second scenario with a higher bid price, calculated by the same engine from overridden inputs.
    higher = calculate_financial_results(
        FinancialInputs(**{**inputs_from_model(model).__dict__, "bid_price": D("150000")})
    )
    base = Scenario(project_id=project.id, financial_model_id=model.id, name="Base", kind="baseline",
                    results=results, calculated_at=utcnow(), engine_version=ENGINE_VERSION)
    alt = Scenario(project_id=project.id, financial_model_id=model.id, name="Higher price", kind="price",
                   results=higher, calculated_at=utcnow(), engine_version=ENGINE_VERSION)
    session.add_all([base, alt])
    session.flush()

    comparison = compare_stored(session, project.id, [base.id, alt.id])
    assert comparison["not_calculated"] == []
    assert comparison["metrics"]["total_cost"] == {base.id: "96395.67", alt.id: "96395.67"}
    assert comparison["metrics"]["profit"] == {base.id: "43604.33", alt.id: "53604.33"}
    assert comparison["metrics"]["pricing_outcome"][alt.id] == "meets_target"
    assert "cost_model" not in comparison["metrics"]  # nested detail is not flattened into metrics
    assert comparison["scenarios"][0]["results"]["cash_flow"]["status"] == "ok"


def test_month_bounds_protect_against_huge_series():
    with pytest.raises(FinanceInputError):
        cf([], duration_months=10**9)
    with pytest.raises(FinanceInputError):
        CostLine(1, "x", "labour", D("1"), D("1"), None, "Verified", 0, 10**9)
    with pytest.raises(FinanceInputError):
        FinancialInputs(duration_months=1201)
    r = cf([mk(1, "1200", start=0, end=1199)], duration_months=1200)  # the maximum is still computed
    assert r.status == "ok" and len(r.months) >= 1200 and r.closing_balance == D("12000") - D("1200")
