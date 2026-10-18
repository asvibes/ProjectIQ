"""contradiction: conflicting extracted facts across documents, without false positives."""
import copy
import random

import pytest

from app.models import Company, Document, ExtractedFact, Project
from app.models.enums import DocumentType, FactType, VerificationStatus
from app.services.verification.contradiction import (
    ConflictKind,
    ConflictScope,
    conflicting_fact_ids,
    detect_contradictions,
)


def fact(id, label="Submission deadline", value="15 March 2026", normalized="2026-03-15", *, doc=1,
         fact_type="date", unit=None, status="Verified", quote_verified=True, **extra):
    return {"id": id, "document_id": doc, "fact_type": fact_type, "label": label, "value": value,
            "normalized_value": normalized, "unit": unit, "verification_status": status,
            "quote_verified": quote_verified, "quotation": f"quote {id}", "page_number": id, "location_ref": f"s{id}", **extra}


def doc(id, *, name=None, type="tender", version=1, project=1, company=None):
    return {"id": id, "original_filename": name or f"doc{id}.pdf", "document_type": type, "version": version,
            "project_id": None if company else project, "company_id": company}


TENDER = doc(1, name="tender.pdf")
ADDENDUM = doc(2, name="addendum1.pdf", type="tender_addendum", version=2)


def ids(report):
    return [c.contradiction_id for c in report.contradictions]


# ------------------------------------------------------------- real conflicts
def test_addendum_changing_a_deadline_is_flagged_with_both_sources():
    report = detect_contradictions(
        [fact(1, doc=1), fact(2, value="29 March 2026", normalized="2026-03-29", doc=2)], [TENDER, ADDENDUM])
    (c,) = report.contradictions
    assert c.kind is ConflictKind.DATE and c.scope is ConflictScope.BETWEEN_DOCUMENTS
    assert c.distinct_values == ("2026-03-15", "2026-03-29")
    assert c.fact_ids == (1, 2) and conflicting_fact_ids(report) == (1, 2)
    first, second = c.sources
    assert (first.document_name, first.document_type, first.page_number, first.location_ref, first.quotation) == \
        ("tender.pdf", "tender", 1, "s1", "quote 1")
    assert (second.document_name, second.document_type, second.document_version, second.value) == \
        ("addendum1.pdf", "tender_addendum", 2, "29 March 2026")
    assert "includes_addendum" in c.flags and "multiple_document_versions" in c.flags
    assert "basis_unverified" not in c.flags and "quotation_unchecked" not in c.flags
    assert report.summary["contradictions"] == 1 and report.summary["comparable_groups"] == 1


def test_numeric_conflict_with_same_unit():
    report = detect_contradictions(
        [fact(1, "Bid bond", "USD 50,000", "50000", fact_type="cost", unit="USD"),
         fact(2, "bid bond", "USD 75,000", "75,000.00", fact_type="cost", unit=" usd ", doc=2)], [TENDER, ADDENDUM])
    (c,) = report.contradictions
    assert c.kind is ConflictKind.VALUE and c.unit == "usd" and c.distinct_values == ("50000", "75000")


def test_three_claims_two_values_is_one_finding_listing_all_sources():
    report = detect_contradictions([fact(1), fact(2, doc=2), fact(3, "submission  DEADLINE.", normalized="2026-04-01", doc=3)],
                                   [TENDER, ADDENDUM, doc(3, name="addendum2.pdf", type="tender_addendum")])
    (c,) = report.contradictions
    assert len(c.sources) == 3 and c.distinct_values == ("2026-03-15", "2026-04-01")


def test_label_matching_ignores_case_spacing_and_punctuation_only():
    report = detect_contradictions([fact(1, "Bid  submission deadline:"), fact(2, "BID SUBMISSION DEADLINE", normalized="2026-03-20", doc=2)])
    assert len(report.contradictions) == 1


def test_conflict_within_one_document_is_labelled_and_noted():
    (c,) = detect_contradictions([fact(1), fact(2, normalized="2026-03-20")]).contradictions
    assert c.scope is ConflictScope.WITHIN_DOCUMENT and any("separate lots" in n for n in c.notes)


def test_unrecorded_source_document_is_unspecified_scope():
    (c,) = detect_contradictions([fact(1, doc=None), fact(2, normalized="2026-03-20", doc=None)]).contradictions
    assert c.scope is ConflictScope.UNSPECIFIED and c.sources[0].document_name is None


# ------------------------------------------------------ no false positives
def test_same_value_in_several_documents_is_agreement():
    facts = [fact(1), fact(2, doc=2), fact(3, "Bid bond", "1500", "1500", fact_type="cost", unit="USD"),
             fact(4, "Bid bond", "1,500.00", "1,500.00", fact_type="cost", unit="USD", doc=2)]
    report = detect_contradictions(facts, [TENDER, ADDENDUM])
    assert report.contradictions == () and report.summary["comparable_groups"] == 2


def test_different_labels_are_never_grouped():
    report = detect_contradictions([fact(1, "Submission deadline"), fact(2, "Clarification deadline", normalized="2026-02-01", doc=2)],
                                   [TENDER, ADDENDUM])
    assert report.contradictions == ()


def test_different_fact_types_with_the_same_label_are_never_grouped():
    report = detect_contradictions([fact(1, "Duration", "90", "90", fact_type="quantity"), fact(2, "Duration", "2026-05-01", "2026-05-01")])
    assert report.contradictions == ()


def test_different_or_missing_units_are_not_compared_and_no_conversion_is_invented():
    report = detect_contradictions([
        fact(1, "Contract value", "USD 1m", "1000000", fact_type="cost", unit="USD"),
        fact(2, "Contract value", "EUR 1m", "900000", fact_type="cost", unit="EUR", doc=2),
        fact(3, "Contract value", "900000", "900000", fact_type="cost", unit=None, doc=2)], [TENDER, ADDENDUM])
    assert report.contradictions == ()
    assert report.summary["labels_with_different_units"] == 1


def test_dates_ignore_the_unit_field():
    assert len(detect_contradictions([fact(1, unit="x"), fact(2, normalized="2026-03-20", unit="y")]).contradictions) == 1


@pytest.mark.parametrize("normalized", [None, "", "15 March 2026", "15/03/2026", "2026-02-30", "2026-3-5", 20260315])
def test_incomplete_or_invalid_dates_are_skipped_not_conflicts(normalized):
    report = detect_contradictions([fact(1), fact(2, normalized=normalized, doc=2)], [TENDER, ADDENDUM])
    assert report.contradictions == ()
    assert [(s.fact_id, s.reason) for s in report.skipped] == [(2, "no_comparable_value")]


@pytest.mark.parametrize("normalized", ["abc", "1e3", "1,50", "1 500", "", None, "USD 5", "1.2.3", "--5"])
def test_unparseable_numbers_are_skipped(normalized):
    report = detect_contradictions([fact(1, "Bond", "5", "5", fact_type="cost"), fact(2, "Bond", "x", normalized, fact_type="cost", doc=2)])
    assert report.contradictions == () and report.skipped[0].reason == "no_comparable_value"


def test_free_text_value_is_never_used_when_normalized_value_is_absent():
    report = detect_contradictions([fact(1, normalized=None, value="15 March 2026"), fact(2, normalized=None, value="29 March 2026", doc=2)])
    assert report.contradictions == () and len(report.skipped) == 2


def test_unsupported_quotation_is_excluded_from_comparison():
    report = detect_contradictions([fact(1), fact(2, normalized="2026-03-29", quote_verified=False, doc=2)], [TENDER, ADDENDUM])
    assert report.contradictions == ()
    assert report.skipped[0].reason == "quotation_not_verified"


def test_rejected_ignored_outdated_and_missing_skipped():
    report = detect_contradictions([
        fact(1), fact(2, normalized="2026-03-29", status="Rejected"),
        fact(3, normalized="2026-04-01", status="Outdated"), fact(4, normalized="2026-04-02", status="Missing")])
    assert report.contradictions == ()
    assert sorted((s.fact_id, s.reason) for s in report.skipped) == [(3, "outdated"), (4, "marked_missing")]
    assert report.summary["ignored_rejected"] == 1


def test_free_text_fact_types_are_not_compared():
    facts = [fact(1, "Scope", "Supply 2 cranes", "a", fact_type="deliverable"), fact(2, "Scope", "Supply 3 cranes", "b", fact_type="deliverable", doc=2)]
    report = detect_contradictions(facts)
    assert report.contradictions == () and report.summary["not_compared_unsupported_type"] == 2


def test_blank_label_is_skipped():
    report = detect_contradictions([fact(1, label=" "), fact(2, label="!!!", normalized="2026-01-01")])
    assert report.contradictions == () and {s.reason for s in report.skipped} == {"no_label"}


def test_single_claim_and_empty_input_have_no_findings():
    assert detect_contradictions([]).contradictions == ()
    assert detect_contradictions([fact(1)]).summary["comparable_groups"] == 0


# ---------------------------------------------------------- scoping / trust
def test_company_facts_are_not_compared_with_tender_facts():
    company_doc = doc(10, name="profile.pdf", type="company_profile", company=5)
    facts = [fact(1, "Annual turnover", "USD 8m", "8000000", fact_type="cost", unit="USD", doc=10),
             fact(2, "Annual turnover", "USD 5m", "5000000", fact_type="cost", unit="USD", doc=1)]
    assert detect_contradictions(facts, [TENDER, company_doc]).contradictions == ()


def test_different_projects_are_not_compared():
    other = doc(3, project=2)
    assert detect_contradictions([fact(1, doc=1), fact(2, normalized="2026-03-29", doc=3)], [TENDER, other]).contradictions == ()


def test_unsupplied_or_ownerless_documents_are_skipped_when_documents_are_given():
    ownerless = {"id": 9, "original_filename": "x.pdf", "document_type": "other", "project_id": None, "company_id": None}
    report = detect_contradictions([fact(1), fact(2, normalized="2026-03-29", doc=7), fact(3, normalized="2026-03-30", doc=9)], [TENDER, ownerless])
    assert report.contradictions == ()
    assert sorted((s.fact_id, s.reason) for s in report.skipped) == [(2, "document_not_provided"), (3, "document_owner_unknown")]


def test_unverified_status_and_unchecked_quotation_are_flagged_not_hidden():
    (c,) = detect_contradictions([fact(1, status="Requires review", quote_verified=None), fact(2, normalized="2026-03-29", doc=2)],
                                 [TENDER, ADDENDUM]).contradictions
    assert {"basis_unverified", "quotation_unchecked"} <= set(c.flags)
    assert c.sources[0].verification_status == "Requires review" and c.sources[0].quote_verified is None


def test_inputs_are_not_modified_and_status_is_not_changed():
    facts = [fact(1, status="Requires review"), fact(2, normalized="2026-03-29", doc=2, status="Requires review")]
    docs = [TENDER, ADDENDUM]
    before = copy.deepcopy((facts, docs))
    detect_contradictions(facts, docs)
    assert (facts, docs) == before


def test_duplicate_fact_ids_are_counted_once():
    report = detect_contradictions([fact(1), fact(1), fact(2, normalized="2026-03-29")])
    assert report.summary["facts_compared"] == 2


def test_result_is_deterministic_regardless_of_input_order():
    facts = [fact(i, f"Deadline {i % 3}", normalized=f"2026-03-{10 + i % 2:02d}", doc=1 + i % 2) for i in range(1, 13)]
    expected = detect_contradictions(facts, [TENDER, ADDENDUM]).to_dict()
    assert expected["contradictions"]
    for seed in range(5):
        shuffled = facts[:]
        random.Random(seed).shuffle(shuffled)
        assert detect_contradictions(shuffled, [TENDER, ADDENDUM]).to_dict() == expected


def test_documents_may_be_a_mapping_and_report_serialises():
    report = detect_contradictions([fact(1), fact(2, normalized="2026-03-29", doc=2)], {1: TENDER, 2: ADDENDUM})
    data = report.to_dict()
    assert data["contradictions"][0]["sources"][1]["document_name"] == "addendum1.pdf"
    assert data["summary"]["version"].startswith("contradiction-")


# --------------------------------------------------------- real ORM objects
def test_works_on_persisted_models(session):
    company = Company(name="Acme")
    session.add(company)
    session.flush()
    project = Project(company_id=company.id, name="Plant")
    session.add(project)
    session.flush()
    tender = Document(project_id=project.id, original_filename="tender.pdf", storage_path="a", document_type=DocumentType.TENDER)
    addendum = Document(project_id=project.id, original_filename="add.pdf", storage_path="b",
                        document_type=DocumentType.TENDER_ADDENDUM, version=2)
    session.add_all([tender, addendum])
    session.flush()
    rows = [
        ExtractedFact(document_id=tender.id, fact_type=FactType.DATE, label="Submission deadline", value="15 March 2026",
                      normalized_value="2026-03-15", quotation="by 15 March 2026", page_number=3, quote_verified=True),
        ExtractedFact(document_id=addendum.id, fact_type=FactType.DATE, label="Submission deadline", value="29 March 2026",
                      normalized_value="2026-03-29", quotation="extended to 29 March 2026", quote_verified=True),
    ]
    session.add_all(rows)
    session.flush()

    report = detect_contradictions(rows, [tender, addendum])
    (c,) = report.contradictions
    assert c.fact_ids == tuple(r.id for r in rows)
    assert c.sources[0].document_type == "tender" and c.sources[1].document_type == "tender_addendum"
    assert c.sources[0].verification_status == VerificationStatus.REQUIRES_REVIEW.value
    assert {"basis_unverified", "includes_addendum"} <= set(c.flags)
    assert all(r.verification_status is VerificationStatus.REQUIRES_REVIEW for r in rows)  # nothing was changed