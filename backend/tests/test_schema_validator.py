"""schema_validator: strict validation of AI-extracted items against the ORM models."""
import json
from datetime import datetime, timezone

import pytest

from app.models import Company, Document, ExtractedFact, Project, Requirement, Risk
from app.models.enums import FactType, RequirementCategory, RequirementOrigin, VerificationStatus
from app.models.risk import RiskCategory
from app.services.ai.extractor import ExtractedDeadline, ExtractedRequirement, ExtractedRisk
from app.services.verification import schema_validator as sv
from app.services.verification.schema_validator import (
    PayloadKind,
    parse_json_payload,
    validate_batch,
    validate_extracted,
    validate_json,
)

QUOTE = "Bids must be submitted by 15 March 2026 at 12:00 noon."


def codes(result):
    return {(i.field, i.code) for i in result.issues}


def req(**overrides):
    base = {"description": "Bidder must hold ISO 9001", "category": "certification", "is_mandatory": True,
            "quotation": "The Contractor shall hold ISO 9001:2015 certification."}
    return {**base, **overrides}


def fact(**overrides):
    base = {"fact_type": "date", "label": "Submission deadline", "value": "15 March 2026",
            "normalized_value": "2026-03-15", "quotation": QUOTE}
    return {**base, **overrides}


def risk(**overrides):
    base = {"title": "Liquidated damages", "category": "contractual", "quotation": "Liquidated damages of 0.5% per week apply."}
    return {**base, **overrides}


# ------------------------------------------------------------------ happy paths
def test_valid_requirement_is_cleaned_and_forced_to_requires_review():
    result = validate_extracted("requirement", req(description="  Bidder must hold ISO 9001  "))
    assert result.ok and result.issues == ()
    assert result.values["description"] == "Bidder must hold ISO 9001"
    assert result.values["category"] is RequirementCategory.CERTIFICATION
    assert result.values["verification_status"] is VerificationStatus.REQUIRES_REVIEW


def test_valid_fact_and_risk():
    assert validate_extracted(PayloadKind.FACT, fact()).ok
    cleaned = validate_extracted(PayloadKind.RISK, risk()).values
    assert cleaned["category"] is RiskCategory.CONTRACTUAL


def test_extractor_output_values_pass_unchanged():
    """The extractor's own ``to_*_values`` output is accepted (contract compatibility)."""
    common = dict(quotation=QUOTE, quote_verified=True, source_filename="t.pdf", chunk_index=0,
                  extractor="extract_deadlines_v1@gemma3:4b", page_number=2, location_ref="Section 4.3")
    deadline = ExtractedDeadline(**common, label="Submission deadline", value="15 March 2026", normalized_value="2026-03-15")
    requirement = ExtractedRequirement(**common, description="Submit by 15 March 2026", category=RequirementCategory.SCHEDULE,
                                       is_mandatory=None, deadline_text="15 March 2026",
                                       deadline=datetime(2026, 3, 15, tzinfo=timezone.utc))
    extracted_risk = ExtractedRisk(**common, title="Late submission", description=None, category=RiskCategory.SCHEDULE)
    for kind, values in (("fact", deadline.to_fact_values()), ("requirement", requirement.to_requirement_values()),
                         ("risk", extracted_risk.to_risk_values())):
        result = validate_extracted(kind, values)
        assert result.ok, (kind, result.issues)
        assert result.values["verification_status"] is VerificationStatus.REQUIRES_REVIEW


def test_unverified_item_without_location_is_valid():
    assert validate_extracted("requirement", req(quote_verified=False)).ok
    assert validate_extracted("requirement", req(quote_verified=None)).ok


def test_blank_optional_text_becomes_none_and_unknown_flag_is_kept_none():
    values = validate_extracted("requirement", req(is_mandatory=None, location_ref="   ")).values
    assert values["is_mandatory"] is None and values["location_ref"] is None


# ------------------------------------------------------- missing / blank / null
@pytest.mark.parametrize("kind,payload,missing", [
    ("requirement", {"quotation": "q"}, "description"),
    ("requirement", {"description": "d"}, "quotation"),
    ("fact", {"label": "l", "value": "v"}, "quotation"),
    ("fact", {"value": "v", "quotation": "v"}, "label"),
    ("risk", {"quotation": "q"}, "title"),
])
def test_missing_required_fields(kind, payload, missing):
    assert (missing, "missing") in codes(validate_extracted(kind, payload))


def test_blank_required_text_and_explicit_null():
    assert ("description", "blank") in codes(validate_extracted("requirement", req(description="   ")))
    assert ("quotation", "blank") in codes(validate_extracted("requirement", req(quotation="")))
    assert ("quotation", "missing") in codes(validate_extracted("requirement", req(quotation=None)))
    assert ("label", "null_not_allowed") in codes(validate_extracted("fact", fact(label=None)))


def test_all_problems_are_reported_together():
    result = validate_extracted("fact", {"label": 5, "bogus": 1, "unit": "x" * 51})
    assert {("label", "wrong_type"), ("bogus", "unknown_field"), ("unit", "too_long"),
            ("value", "missing"), ("quotation", "missing")} <= codes(result)
    assert result.values is None and not result.ok


# --------------------------------------------------------------- invalid types
@pytest.mark.parametrize("field,value,code", [
    ("description", 123, "wrong_type"),
    ("is_mandatory", "true", "wrong_type"),
    ("is_mandatory", 1, "wrong_type"),
    ("category", "made_up", "invalid_choice"),
    ("category", 7, "wrong_type"),
    ("page_number", "2", "wrong_type"),
    ("page_number", 2.0, "wrong_type"),
    ("page_number", True, "wrong_type"),
    ("deadline", "15 March 2026", "wrong_type"),
    ("deadline", datetime(2026, 3, 15), "naive_datetime"),
    ("deadline", "2026-03-15", "naive_datetime"),
    ("quote_verified", "yes", "wrong_type"),
    ("code", "R" * 33, "too_long"),
    ("description", "a\x00b", "invalid_characters"),
])
def test_invalid_types_and_values(field, value, code):
    assert (field, code) in codes(validate_extracted("requirement", req(**{field: value})))


def test_page_number_must_be_positive_and_needs_verified_quote():
    assert ("page_number", "out_of_range") in codes(validate_extracted("requirement", req(page_number=0, quote_verified=True)))
    assert validate_extracted("requirement", req(page_number=1, quote_verified=True)).ok


def test_aware_iso_string_deadline_is_accepted():
    values = validate_extracted("requirement", req(deadline="2026-03-15T00:00:00Z")).values
    assert values["deadline"] == datetime(2026, 3, 15, tzinfo=timezone.utc)


def test_error_messages_never_echo_submitted_values():
    secret = "SECRET-TENDER-TEXT"
    result = validate_extracted("requirement", req(category=secret, is_mandatory=secret, page_number=secret, bogus=secret))
    assert result.issues and all(secret not in str(i.to_dict()) for i in result.issues)


# ------------------------------------------------------- extraction contract
@pytest.mark.parametrize("field,value", [
    ("match_status", "Met"), ("evidence_summary", "x"), ("notes", "x"), ("assigned_role", "x"),
    ("last_verified_at", datetime(2026, 1, 1, tzinfo=timezone.utc)),
])
def test_requirement_fields_a_person_owns_are_not_permitted(field, value):
    assert (field, "not_permitted") in codes(validate_extracted("requirement", req(**{field: value})))


@pytest.mark.parametrize("field", ["probability", "impact", "score", "status", "mitigation", "owner"])
def test_risk_ratings_and_scores_are_not_permitted(field):
    assert (field, "not_permitted") in codes(validate_extracted("risk", risk(**{field: 3})))


def test_model_cannot_mark_an_item_verified_or_manual():
    for status in ("Verified", VerificationStatus.VERIFIED, "Rejected"):
        assert ("verification_status", "not_permitted_value") in codes(
            validate_extracted("requirement", req(verification_status=status)))
    assert validate_extracted("requirement", req(verification_status="Requires review")).ok
    assert ("origin", "not_permitted_value") in codes(validate_extracted("requirement", req(origin="manual")))
    assert validate_extracted("requirement", req(origin=RequirementOrigin.EXTRACTED)).ok


def test_location_requires_verified_quotation():
    for extra in ({"page_number": 3}, {"location_ref": "Section 4"}):
        for verified in (False, None):
            assert ("location_ref", "location_without_verified_quote") in codes(
                validate_extracted("requirement", req(quote_verified=verified, **extra)))
    assert validate_extracted("requirement", req(quote_verified=True, page_number=3, location_ref="Section 4")).ok


# ------------------------------------------------------------------- facts
def test_fact_value_must_be_in_quotation_with_normalisation():
    assert ("value", "value_not_in_quotation") in codes(validate_extracted("fact", fact(value="1 April 2026", normalized_value=None)))
    assert validate_extracted("fact", fact(value="15  March\u00a02026")).ok  # spacing differences are fine


@pytest.mark.parametrize("normalized,code", [
    ("2026-02-30", "invalid_date"), ("15/03/2026", "invalid_date"), ("2026-3-15", "invalid_date"),
    ("1850-03-15", "invalid_date"), ("2027-03-15", "year_not_in_value"),
])
def test_date_fact_normalized_value_must_be_strict_and_supported(normalized, code):
    result = validate_extracted("fact", fact(normalized_value=normalized))
    assert ("normalized_value", code) in codes(result)


def test_non_date_fact_normalized_value_is_not_date_checked():
    quote = "The bid bond shall be 2% of the tender sum."
    assert validate_extracted("fact", fact(fact_type="cost", label="Bid bond", value="2%", normalized_value="0.02", quotation=quote)).ok


# ------------------------------------------------------- malformed input
@pytest.mark.parametrize("data", [None, "text", 5, ["a"], [("description", "x")]])
def test_non_object_items_are_rejected(data):
    assert codes(validate_extracted("requirement", data)) == {("", "not_an_object")}


def test_non_text_keys_are_rejected():
    assert ("", "bad_key") in codes(validate_extracted("requirement", {1: "x", **req()}))


def test_unknown_kind_is_a_programming_error():
    with pytest.raises(ValueError):
        validate_extracted("deadline", {})



@pytest.mark.parametrize(
    "payload,code",
    [
        ("", "invalid_json"),
        ("not json", "invalid_json"),
        ('{"a": NaN}', "invalid_json"),
        ('{"a": Infinity}', "invalid_json"),
        (b"\xff\xfe", "invalid_json"),
        pytest.param(
            "[" * 100_000,
            "invalid_json",
            id="deep-invalid-json",
        ),
        (123, "wrong_type"),
        pytest.param(
            "x" * (sv.MAX_JSON_BYTES + 1),
            "too_large",
            id="oversized-payload",
        ),
    ],
)
def test_json_payload_guards(payload, code):
    data, issue = parse_json_payload(payload)
    assert data is None and issue.code == code




def test_validate_json_accepts_fenced_json_and_rejects_non_objects():
    assert validate_json("requirement", "```json\n" + json.dumps(req()) + "\n```").ok
    assert validate_json("requirement", json.dumps(req()).encode()).ok
    assert codes(validate_json("requirement", "[1, 2]")) == {("", "not_an_object")}
    assert codes(validate_json("requirement", "oops")) == {("", "invalid_json")}


# -------------------------------------------------------------------- batches
def test_batch_separates_accepted_and_rejected_and_keeps_positions():
    batch = validate_batch("requirement", [req(), {"description": "no quote"}, "junk", req(description="Second")])
    assert [i for i, _ in batch.accepted] == [0, 3]
    assert [r.index for r in batch.rejected] == [1, 2]
    assert not batch.ok
    assert batch.to_dict()["accepted_indexes"] == [0, 3]


def test_batch_from_json_with_key_and_bare_list():
    text = json.dumps({"requirements": [req()]})
    assert validate_batch("requirement", text, key="requirements").ok
    assert validate_batch("requirement", json.dumps([req()])).ok
    assert validate_batch("requirement", {"requirements": [req()]}, key="requirements").ok


@pytest.mark.parametrize("items,code", [
    ({"requirements": []}, "not_a_list"), ("{}", "not_a_list"), (None, "not_a_list"), (5, "not_a_list"),
    ("{bad", "invalid_json"),
])
def test_batch_level_problems(items, code):
    batch = validate_batch("requirement", items)
    assert not batch.ok and batch.issues[0].code == code


def test_batch_limit_is_reported_not_silent():
    batch = validate_batch("requirement", [req() for _ in range(5)], max_items=3)
    assert len(batch.accepted) == 3 and batch.issues[0].code == "too_many_items" and not batch.ok


def test_empty_batch_is_ok():
    assert validate_batch("risk", []).ok


# ------------------------------------------------------- model compatibility
def test_permitted_fields_exist_on_the_models():
    for spec in sv._SPECS.values():
        assert spec.permitted <= set(spec.model.__table__.columns.keys())
        assert spec.non_blank <= spec.permitted


def test_cleaned_values_persist_through_the_real_models(session):
    company = Company(name="Acme")
    session.add(company)
    session.flush()
    project = Project(company_id=company.id, name="Plant")
    session.add(project)
    session.flush()
    document = Document(project_id=project.id, original_filename="t.pdf", storage_path="x/t.pdf")
    session.add(document)
    session.flush()

    requirement = validate_extracted("requirement", req(quote_verified=True, page_number=2, location_ref="Section 4",
                                                        deadline="2026-03-15T00:00:00+00:00")).values
    fact_values = validate_extracted("fact", fact(quote_verified=True, page_number=2)).values
    risk_values = validate_extracted("risk", risk()).values
    rows = [
        Requirement(project_id=project.id, code="REQ-001", **requirement),
        ExtractedFact(document_id=document.id, **fact_values),
        Risk(project_id=project.id, code="RISK-001", **risk_values),
    ]
    session.add_all(rows)
    session.flush()  # the database CHECK constraints accept everything the validator accepts
    assert all(r.verification_status is VerificationStatus.REQUIRES_REVIEW for r in rows)
    assert rows[1].fact_type is FactType.DATE