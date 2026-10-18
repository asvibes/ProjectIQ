"""equipment_options: equipment needs against the company register and tender requirements."""
import copy
import json
from datetime import date
from decimal import Decimal

import pytest

from app.models import Company, CompanyEquipment, Project, ProjectResource
from app.models.enums import EquipmentOwnership, VerificationStatus
from app.services.analysis.equipment_options import (
    SUGGESTED_OPTIONS,
    EquipmentCoverage,
    analyse_equipment,
)
from app.services.analysis.requirement_matcher import match_requirements

V = "Verified"


def res(id, name="Excavator", required=1, *, type="equipment", status=V, **kw):
    return {"id": id, "name": name, "resource_type": type, "required_quantity": required,
            "verification_status": status, **kw}


def eq(id, name="Excavator", quantity=2, ownership="owned", *, status=V, **kw):
    return {"id": id, "name": name, "quantity": quantity, "ownership": ownership,
            "verification_status": status, **kw}


def one(resources, items, **kw):
    report = analyse_equipment(resources, items, **kw)
    assert len(report.items) == 1
    return report.items[0]


# ------------------------------------------------------------------- coverage
def test_covered_by_owned_register_quantity():
    a = one([res(1, required=2)], [eq(10, quantity=3)])
    assert a.coverage is EquipmentCoverage.COVERED and (a.available, a.surplus, a.shortfall) == (3, 1, 0)
    assert a.availability_source == "company_equipment" and a.company_equipment_id == 10
    assert a.suggested_options == () and a.flags == ("register_quantity_used",)
    assert any("other projects" in n for n in a.notes)


def test_shortfall_offers_options_to_evaluate_and_lists_missing_cost_and_period():
    a = one([res(1, required=3)], [eq(10, quantity=1)])
    assert a.coverage is EquipmentCoverage.SHORTFALL and (a.shortfall, a.surplus) == (2, None)
    assert a.suggested_options == SUGGESTED_OPTIONS
    assert any("Unit cost" in m for m in a.missing_information)
    assert any("Required period" in m for m in a.missing_information)


def test_known_cost_and_period_are_not_reported_missing_and_cost_is_never_computed():
    a = one([res(1, required=3, unit_cost=Decimal("1200.50"), unit="month", currency="USD",
                 required_from=date(2026, 5, 1), required_to=date(2026, 8, 1))], [eq(10, quantity=1)])
    assert a.missing_information == ()
    assert (a.unit_cost, a.unit, a.currency) == (Decimal("1200.50"), "month", "USD")
    assert a.to_dict()["unit_cost"] == "1200.50"  # shown as recorded; no total is derived


@pytest.mark.parametrize("cost,expected", [("900", Decimal("900")), (900, Decimal("900")), (None, None),
                                           ("abc", None), (-5, None), (True, None), ("NaN", None)])
def test_unit_cost_parsing_never_defaults_to_zero(cost, expected):
    assert one([res(1, required=2, unit_cost=cost)], [eq(10, quantity=1)]).unit_cost == expected


def test_required_zero_is_not_required():
    a = one([res(1, required=0)], [eq(10)])
    assert a.coverage is EquipmentCoverage.NOT_REQUIRED and a.suggested_options == ()


# ----------------------------------------------------------- unknown is not zero
def test_unknown_ownership_quantity_is_not_capacity():
    a = one([res(1, required=2)], [eq(10, quantity=5, ownership="unknown")])
    assert a.coverage is EquipmentCoverage.UNKNOWN and a.available is None and a.shortfall is None
    assert a.recorded_quantity == 5 and "ownership_unknown" in a.flags
    assert any("Ownership" in m for m in a.missing_information)
    assert a.suggested_options == ()


def test_recorded_zero_is_a_real_zero_even_with_unknown_ownership():
    a = one([res(1, required=1)], [eq(10, quantity=0, ownership="unknown")])
    assert a.coverage is EquipmentCoverage.SHORTFALL and a.available == 0 and a.shortfall == 1


def test_no_company_record_is_unknown_not_a_shortfall():
    a = one([res(1, "Tower crane", required=1)], [eq(10, "Excavator")])
    assert a.coverage is EquipmentCoverage.UNKNOWN and "no_company_equipment" in a.flags
    assert a.company_equipment_id is None and a.shortfall is None


def test_person_entered_availability_is_used_when_the_register_is_silent():
    a = one([res(1, "Tower crane", required=2, available_quantity=2)], [])
    assert a.coverage is EquipmentCoverage.COVERED and a.availability_source == "project_resource"
    assert "no_company_equipment" in a.flags and a.available == 2


def test_person_entered_zero_is_a_real_zero():
    assert one([res(1, required=1, available_quantity=0)], [eq(10, quantity=4)]).coverage is EquipmentCoverage.SHORTFALL


def test_explicit_availability_wins_over_register_when_consistent():
    a = one([res(1, required=2, available_quantity=1)], [eq(10, quantity=3)])
    assert a.available == 1 and a.availability_source == "project_resource" and a.shortfall == 1


# -------------------------------------------------------------------- conflicts
def test_availability_above_the_register_quantity_is_a_conflict_with_both_figures():
    a = one([res(1, required=2, available_quantity=5)], [eq(10, quantity=3)])
    assert a.coverage is EquipmentCoverage.CONFLICTING and a.candidate_available == (5, 3)
    assert a.available is None and a.shortfall is None and a.surplus is None
    assert "conflicting_figures" in a.flags and a.suggested_options == ()


def test_conflicting_company_record_is_not_used():
    a = one([res(1, required=1)], [eq(10, quantity=3, status="Conflicting")])
    assert a.coverage is EquipmentCoverage.CONFLICTING and {"conflicting_record", "conflicting_figures"} <= set(a.flags)


# ------------------------------------------------------------ ownership / trust
def test_leased_units_count_but_are_flagged_for_lease_term():
    a = one([res(1, required=1)], [eq(10, quantity=1, ownership="leased")])
    assert a.coverage is EquipmentCoverage.COVERED and "leased_capacity" in a.flags
    assert any("lease term" in n for n in a.notes)


def test_unverified_records_are_analysed_but_flagged():
    a = one([res(1, required=1)], [eq(10, quantity=2, status="Requires review")])
    assert a.coverage is EquipmentCoverage.COVERED and "basis_unverified" in a.flags
    assert "basis_unverified" not in one([res(1)], [eq(10)]).flags
    b = one([res(1, available_quantity=1, status="Estimated")], [eq(10, quantity=2)])
    assert "basis_unverified" in b.flags


def test_rejected_records_are_ignored():
    report = analyse_equipment([res(1, status="Rejected"), res(2, "Crane")], [eq(10, "Crane", status="Rejected")])
    assert [i.resource_id for i in report.items] == [2] and report.items[0].coverage is EquipmentCoverage.UNKNOWN


def test_only_equipment_resources_are_analysed():
    report = analyse_equipment([res(1, "Welder", type="personnel"), res(2, "Hauler", type="subcontractor"), res(3)], [eq(10)])
    assert [i.resource_id for i in report.items] == [3]


# ------------------------------------------------------------------------ linking
def test_explicit_link_beats_name_and_missing_link_is_explained():
    items = [eq(10, "Excavator", 1), eq(11, "Digger", 4)]
    assert one([res(1, "Excavator", 3, company_equipment_id=11)], items).company_equipment_id == 11
    a = one([res(1, "Excavator", 3, company_equipment_id=99)], items)
    assert a.company_equipment_id is None and a.coverage is EquipmentCoverage.UNKNOWN
    assert any("not found" in n for n in a.notes)
    b = one([res(1, "Excavator", 3, company_equipment_id=12)], [eq(12, status="Rejected")])
    assert b.company_equipment_id is None


@pytest.mark.parametrize("name", ["excavator", "  EXCAVATOR ", "Excavator"])
def test_name_and_type_matching_is_exact_ignoring_case_and_spacing(name):
    assert one([res(1, name)], [eq(10, "Excavator")]).company_equipment_id == 10
    assert one([res(1, name)], [eq(10, "CAT 320D", equipment_type="Excavator")]).company_equipment_id == 10


def test_partial_names_are_not_matched():
    assert one([res(1, "Tower crane")], [eq(10, "Tower crane TC-80")]).company_equipment_id is None


def test_ambiguous_name_is_not_guessed_or_summed():
    a = one([res(1, "Excavator", 3)], [eq(10, "Excavator", 2, "owned"), eq(11, "Excavator", 2, "leased")])
    assert a.coverage is EquipmentCoverage.UNKNOWN and "ambiguous_company_match" in a.flags
    assert a.company_equipment_id is None and any("2 company equipment records" in n for n in a.notes)


# ---------------------------------------------------------------- shared capacity
def test_two_resources_on_one_item_can_overcommit_it():
    report = analyse_equipment(
        [res(1, "Excavator", 2, company_equipment_id=10, required_from=date(2026, 5, 1), required_to=date(2026, 6, 30)),
         res(2, "Digger", 1, company_equipment_id=10, required_from=date(2026, 6, 1), required_to=date(2026, 7, 31))],
        [eq(10, quantity=2)])
    (s,) = report.shared_capacity
    assert (s.peak_demand, s.available, s.overcommitted, s.shortfall) == (3, 2, True, 1)
    assert s.peak_on == date(2026, 6, 1) and not s.assumed_concurrent
    assert all(i.coverage is EquipmentCoverage.COVERED for i in report.items)  # each fits alone
    assert report.summary["shared_capacity_overcommitted"] == ["Excavator"]


def test_non_overlapping_periods_fit_and_open_periods_are_assumed_to_overlap():
    items = [eq(10, quantity=2)]
    apart = analyse_equipment(
        [res(1, required=2, company_equipment_id=10, required_from=date(2026, 1, 1), required_to=date(2026, 2, 1)),
         res(2, "Digger", 2, company_equipment_id=10, required_from=date(2026, 3, 1), required_to=date(2026, 4, 1))], items)
    assert not apart.shared_capacity[0].overcommitted
    open_ = analyse_equipment([res(1, required=2, company_equipment_id=10), res(2, "Digger", 2, company_equipment_id=10)], items)
    assert open_.shared_capacity[0].overcommitted and open_.shared_capacity[0].assumed_concurrent


def test_shared_capacity_with_unusable_register_quantity_is_not_confirmed():
    for item in (eq(10, quantity=2, ownership="unknown"), eq(10, quantity=2, status="Conflicting")):
        (s,) = analyse_equipment([res(1, company_equipment_id=10), res(2, "Digger", company_equipment_id=10)], [item]).shared_capacity
        assert s.available is None and not s.overcommitted and "unknown" in s.note


# ------------------------------------------------------------ tender requirements
COMPANY = {"equipment": [eq(7, "Tower Crane TC-80", 2, equipment_type="tower crane", capacity="80 t"),
                         eq(8, "Excavator", 1, "leased")],
           "certifications": [], "workforce_roles": [], "past_projects": []}
REQS = [{"id": 1, "code": "REQ-001", "description": "The contractor shall own at least 2 tower crane.",
         "category": "technical", "verification_status": V},
        {"id": 2, "code": "REQ-002", "description": "Bidder must have 1 excavator available.",
         "category": "technical", "verification_status": V}]


def test_requirements_link_through_real_matcher_evidence():
    results = match_requirements(REQS, COMPANY, as_of=date(2026, 10, 18))
    report = analyse_equipment([res(1, "Tower Crane TC-80", 2)], COMPANY["equipment"], results)
    (a,) = report.items
    assert [(r.requirement_code, r.equipment_id, r.match_status) for r in a.requirements] == [("REQ-001", 7, "Met")]
    assert a.recorded_capacity == "80 t"  # context only
    # the excavator requirement cites equipment no resource line draws on
    assert [(r.requirement_code, r.equipment_id) for r in report.unlinked_requirements] == [("REQ-002", 8)]
    assert report.summary["unlinked_requirement_codes"] == ["REQ-002"]


def test_status_is_the_matchers_not_rederived():
    fake = [{"requirement_code": "REQ-9", "requirement_id": 9, "status": "Unknown", "needs_verification": True,
             "conflict": False, "evidence": [{"kind": "equipment", "record_id": 10, "label": "Excavator"},
                                             {"kind": "certification", "record_id": 3, "label": "ISO"}]}]
    (a,) = analyse_equipment([res(1, required=9)], [eq(10, quantity=1)], fake).items
    assert a.coverage is EquipmentCoverage.SHORTFALL  # coverage is the resource's, independent of the requirement
    assert [(r.match_status, r.needs_verification) for r in a.requirements] == [("Unknown", True)]


def test_not_applicable_requirements_and_other_evidence_kinds_are_skipped():
    fake = [{"requirement_code": "R1", "status": "Not applicable", "evidence": [{"kind": "equipment", "record_id": 10, "label": "x"}]},
            {"requirement_code": "R2", "status": "Met", "evidence": [{"kind": "certification", "record_id": 10, "label": "x"}]}]
    report = analyse_equipment([res(1)], [eq(10)], fake)
    assert report.items[0].requirements == () and report.unlinked_requirements == ()


def test_nothing_is_inferred_without_match_results():
    report = analyse_equipment([res(1)], [eq(10)])
    assert report.items[0].requirements == () and report.unlinked_requirements == ()


# ------------------------------------------------------------------ report
def test_summary_marks_shortfall_as_a_lower_bound_while_anything_is_unknown():
    report = analyse_equipment(
        [res(1, "Crane", 3), res(2, "Excavator", 4), res(3, "Roller", 1), res(4, "Grader", 1, available_quantity=9)],
        [eq(10, "Crane", 1), eq(11, "Excavator", 4), eq(12, "Roller", 5, "unknown"), eq(13, "Grader", 2)])
    s = report.summary
    assert s["by_coverage"] == {"Covered": 1, "Shortfall": 1, "Unknown availability": 1, "Conflicting": 1, "Not required": 0}
    assert s["known_shortfall_total"] == 2 and s["shortfall_is_lower_bound"] is True
    assert s["resources_with_unknown_availability"] == ["Roller"] and s["resources_with_conflicts"] == ["Grader"]
    assert s["version"].startswith("equipment-options-") and "no costs are computed" in s["basis"]


def test_no_lower_bound_when_everything_is_known():
    report = analyse_equipment([res(1, required=3)], [eq(10, quantity=1)])
    assert report.summary["shortfall_is_lower_bound"] is False and report.summary["known_shortfall_total"] == 2


def test_empty_inputs():
    report = analyse_equipment([], [])
    assert report.items == () and report.summary["equipment_resources"] == 0


def test_deterministic_unmodified_inputs_and_json_serialisable():
    resources = [res(i, f"Item {i % 3}", 1 + i % 4, unit_cost=Decimal("10.00")) for i in range(1, 9)]
    items = [eq(20 + i, f"Item {i}", i) for i in range(3)]
    before = copy.deepcopy((resources, items))
    first = analyse_equipment(resources, items).to_dict()
    assert (resources, items) == before
    assert analyse_equipment(list(reversed(resources)), list(reversed(items))).to_dict() == first
    json.dumps(first)


# ------------------------------------------------------------ real ORM objects
def test_works_on_persisted_models(session):
    company = Company(name="Acme")
    session.add(company)
    session.flush()
    project = Project(company_id=company.id, name="Plant")
    session.add(project)
    session.flush()
    crane = CompanyEquipment(company_id=company.id, name="Mobile crane", quantity=1, ownership=EquipmentOwnership.OWNED)
    pump = CompanyEquipment(company_id=company.id, name="Concrete pump", quantity=1)  # ownership defaults to unknown
    crane.mark_verified()
    session.add_all([crane, pump])
    session.flush()
    rows = [
        ProjectResource(project_id=project.id, resource_type="equipment", name="Mobile crane", required_quantity=2,
                        company_equipment_id=crane.id, unit_cost=Decimal("5000"), currency="USD"),
        ProjectResource(project_id=project.id, resource_type="equipment", name="Concrete pump", required_quantity=1),
        ProjectResource(project_id=project.id, resource_type="personnel", name="Foreman", required_quantity=1),
    ]
    session.add_all(rows)
    session.flush()

    report = analyse_equipment(rows, [crane, pump])
    by_name = {i.name: i for i in report.items}
    assert set(by_name) == {"Mobile crane", "Concrete pump"}
    c, p = by_name["Mobile crane"], by_name["Concrete pump"]
    assert (c.coverage, c.shortfall, c.ownership, c.unit_cost) == (EquipmentCoverage.SHORTFALL, 1, "owned", Decimal("5000.00"))
    assert "basis_unverified" not in c.flags  # the register record was verified; the resource supplies no figure of its own
    assert p.coverage is EquipmentCoverage.UNKNOWN and p.company_equipment_id == pump.id
    assert {"ownership_unknown", "basis_unverified"} <= set(p.flags)  # the pump record is still Requires review
    assert all(r.verification_status is VerificationStatus.REQUIRES_REVIEW for r in (pump, *rows))  # nothing was changed