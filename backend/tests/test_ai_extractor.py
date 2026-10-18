"""extractor: validation, quote verification, provenance and failure handling (Ollama mocked)."""
from datetime import datetime, timezone

import pytest

from app.models import (
    Company,
    Document,
    ExtractedFact,
    Project,
    Requirement,
    RequirementCategory,
    Risk,
    VerificationStatus,
)
from app.models.enums import FactType
from app.models.risk import RiskCategory
from app.services.ai import extractor as ex
from app.services.ai.ollama_client import (
    OllamaModelNotFoundError,
    OllamaResponseError,
    OllamaTimeoutError,
    OllamaUnavailableError,
)
from app.services.ingestion.sanitizer import ExtractedDocument, ExtractionStatus, SegmentKind, TextSegment
from tests.ai_helpers import FakeOllama, json_reply, make_chunks, make_client, make_sheet_chunks, text_reply

CERT = "The Contractor shall hold ISO 9001:2015 certification at the time of bid submission."
DUE = "Bids must be submitted by 15 March 2026 at 12:00 noon."
PAGE_1 = f"4.2 {CERT}\n4.3 {DUE}"
PAGE_2 = "7.1 Liquidated damages of 0.5% of the contract price per week of delay apply, up to a maximum of 10%."


def req(**overrides):
    base = {
        "description": "Bidder must hold ISO 9001:2015",
        "category": "certification",
        "is_mandatory": True,
        "deadline_text": None,
        "deadline": None,
        "quotation": CERT,
    }
    return {**base, **overrides}


def run_requirements(items, pages=(PAGE_1,), **kw):
    fake = FakeOllama(*[json_reply({"requirements": items}) for _ in make_chunks(pages)])
    result = ex.extract_requirements(make_chunks(pages), client=make_client(fake), **kw)
    return result, fake


# --- happy path and provenance --------------------------------------------------------------
def test_extracts_a_verified_requirement_with_chunk_derived_location():
    # The model claims page 99 and a location; none of that is read.
    result, fake = run_requirements([req(page_number=99, location_ref="Section 99")])
    (item,) = result.items
    assert item.description == "Bidder must hold ISO 9001:2015"
    assert item.category is RequirementCategory.CERTIFICATION and item.is_mandatory is True
    assert item.quote_verified is True and item.quotation == CERT
    assert (item.page_number, item.location_ref) == (1, "page 1")
    assert item.source_filename == "tender.pdf" and item.chunk_index == 0
    assert item.extractor == "extract_requirements_v1@gemma3:4b" == result.extractor
    assert result.complete and result.rejected == () and result.unverified_count == 0
    assert result.prompt == "extract_requirements_v1" and result.chunks_processed == 1


def test_each_chunk_gets_its_own_page_and_the_prompt_fences_the_document():
    pages = ["A" * 60 + " " + CERT, PAGE_2 + " z" * 60]
    result, fake = run_requirements([req()], pages=pages, )
    # both chunks return the same quotation; only page 1's chunk contains it
    assert [i.quote_verified for i in result.items] == [True]
    assert len(fake.calls) == 2
    first = fake.prompts[0]
    assert "<<<BEGIN UNTRUSTED DOCUMENT EXCERPT" in first and "<<<END UNTRUSTED DOCUMENT EXCERPT" in first
    assert 'location="page 1"' in first
    assert "UNTRUSTED" in fake.systems[0] and "never instructions" in fake.systems[0]
    assert fake.calls[0]["payload"]["format"] == "json"


def test_page_two_quotation_is_cited_to_page_two():
    pages = ["B" * 200, PAGE_2]
    fake = FakeOllama(json_reply({"risks": []}), json_reply({"risks": [{
        "title": "Liquidated damages", "description": "Damages per week of delay.", "category": "contractual",
        "quotation": "Liquidated damages of 0.5% of the contract price per week of delay",
    }]}))
    result = ex.extract_risks(make_chunks(pages), client=make_client(fake))
    (risk,) = result.items
    assert risk.quote_verified and (risk.page_number, risk.location_ref) == (2, "page 2")
    assert risk.category is RiskCategory.CONTRACTUAL


def test_worksheet_row_location_comes_from_the_row():
    chunks = make_sheet_chunks([("Sheet BOQ!A2:D2", "Item 1 | Excavation | 500 | m3"),
                                ("Sheet BOQ!A3:D3", "Item 14 | Structural steel, Grade S355 | 120 | tonnes")])
    fake = FakeOllama(json_reply({"requirements": [req(quotation="Structural steel, Grade S355 | 120 | tonnes")]}))
    (item,) = ex.extract_requirements(chunks, client=make_client(fake)).items
    assert item.quote_verified and item.location_ref == "Sheet BOQ!A3:D3" and item.sheet_name == "BOQ"
    assert item.page_number is None


def test_quotation_with_different_spacing_quotes_and_case_still_verifies():
    q = "the  contractor SHALL hold ISO 9001:2015   certification"
    (item,) = run_requirements([req(quotation=q)])[0].items
    assert item.quote_verified and item.page_number == 1


def test_quotation_spanning_two_segments_is_cited_to_the_chunk():
    chunks = make_chunks(["First sentence on page one is long enough.", "Second sentence starts on page two."], max_chars=1000)
    assert len(chunks) == 1
    exact = "long enough.\n\nSecond sentence starts on page two."  # copied exactly: cited where it starts
    spaced = "long enough. Second sentence starts on page two."  # same words, different spacing
    fake = FakeOllama(json_reply({"requirements": [req(quotation=exact), req(description="b", quotation=spaced)]}))
    first, second = ex.extract_requirements(chunks, client=make_client(fake)).items
    assert first.quote_verified and (first.page_number, first.location_ref) == (1, "page 1")
    assert second.quote_verified and second.page_number is None and second.location_ref == "pages 1-2"


def test_extract_from_an_extracted_document_and_empty_documents_make_no_model_call():
    doc = ExtractedDocument("t.txt", "txt", ExtractionStatus.OK,
                            [TextSegment(CERT, SegmentKind.PARAGRAPH, "t.txt", location_ref="lines 1-1")])
    fake = FakeOllama(json_reply({"requirements": [req()]}))
    assert len(ex.extract_requirements(doc, client=make_client(fake)).items) == 1

    empty = ExtractedDocument("s.pdf", "pdf", ExtractionStatus.NO_EXTRACTABLE_TEXT)
    silent = FakeOllama()
    result = ex.extract_requirements(empty, client=make_client(silent))
    assert result.items == () and result.complete and silent.calls == []


# --- evidence rules ---------------------------------------------------------------------------
def test_a_fabricated_quotation_is_flagged_not_hidden_and_has_no_location():
    result, _ = run_requirements([req(quotation="The Contractor must provide a 50 year warranty.")])
    (item,) = result.items
    assert item.quote_verified is False and item.page_number is None and item.location_ref is None
    assert result.unverified_count == 1


@pytest.mark.parametrize("quote", ["the", "ISO 9001", "x" * 2500])
def test_too_short_or_too_long_quotations_prove_nothing(quote):
    (item,) = run_requirements([req(quotation=quote)])[0].items
    assert item.quote_verified is False


def test_items_without_a_quotation_or_with_wrong_types_are_rejected():
    result, _ = run_requirements([
        req(quotation=""),
        {k: v for k, v in req().items() if k != "quotation"},
        req(description=None),
        req(description=["a"]),
        "just a string",
        req(description="d" * 2001),
        req(),
    ])
    assert len(result.items) == 1 and len(result.rejected) == 6
    assert all("schema" in r.reason for r in result.rejected)
    assert all(CERT not in r.reason for r in result.rejected)  # reasons never echo content


def test_unknown_category_becomes_other_and_non_boolean_mandatory_becomes_unknown():
    (a, b, c) = run_requirements([
        req(description="a", category="invented", quotation=CERT, is_mandatory="yes"),
        req(description="b", category=None, is_mandatory=False),
        req(description="c", is_mandatory=None),
    ])[0].items
    assert a.category is RequirementCategory.OTHER and a.is_mandatory is None
    assert b.category is RequirementCategory.OTHER and b.is_mandatory is False
    assert c.is_mandatory is None


def test_unexpected_extra_fields_are_ignored_and_never_applied():
    (item,) = run_requirements([req(verification_status="Verified", match_status="Met", id=7)])[0].items
    assert item.to_requirement_values()["verification_status"] is VerificationStatus.REQUIRES_REVIEW
    assert "match_status" not in item.to_requirement_values()


def test_deadline_needs_wording_in_the_quote_and_a_visible_year():
    q = f"{DUE}"
    good = req(quotation=q, deadline_text="15 March 2026", deadline="2026-03-15")
    no_wording = req(description="b", quotation=q, deadline_text="1 April 2026", deadline="2026-04-01")
    wrong_year = req(description="c", quotation=q, deadline_text="15 March 2026", deadline="2025-03-15")
    bad_format = req(description="d", quotation=q, deadline_text="15 March 2026", deadline="15/03/2026")
    impossible = req(description="e", quotation=q, deadline_text="15 March 2026", deadline="2026-02-30")
    a, b, c, d, e = run_requirements([good, no_wording, wrong_year, bad_format, impossible])[0].items
    assert a.deadline == datetime(2026, 3, 15, tzinfo=timezone.utc) and a.deadline_text == "15 March 2026"
    assert b.deadline is None and b.deadline_text is None
    assert c.deadline is None and c.deadline_text == "15 March 2026"
    assert d.deadline is None and e.deadline is None


def test_duplicates_across_chunks_are_collapsed_and_oversized_lists_are_capped():
    pages = [CERT + " x" * 20, CERT + " y" * 20]
    fake = FakeOllama(json_reply({"requirements": [req()]}), json_reply({"requirements": [req()]}))
    assert len(ex.extract_requirements(make_chunks(pages), client=make_client(fake)).items) == 1

    many = [req(description=f"requirement {i}") for i in range(ex.MAX_ITEMS_PER_CHUNK + 5)]
    result, _ = run_requirements(many)
    assert len(result.items) == ex.MAX_ITEMS_PER_CHUNK
    assert any("extras ignored" in r.reason for r in result.rejected)


def test_a_bare_list_is_accepted_and_an_empty_list_is_a_valid_answer():
    fake = FakeOllama(json_reply([req()]))
    assert len(ex.extract_requirements(make_chunks([PAGE_1]), client=make_client(fake)).items) == 1
    result, _ = run_requirements([])
    assert result.items == () and result.complete


# --- failures -----------------------------------------------------------------------------------
def test_a_malformed_chunk_is_recorded_and_the_others_still_count():
    pages = [PAGE_1, "Another page of boilerplate text. " * 6]
    fake = FakeOllama(json_reply({"requirements": [req()]}), text_reply("I cannot do that"))
    result = ex.extract_requirements(make_chunks(pages), client=make_client(fake))
    assert len(result.items) == 1 and not result.complete
    assert [f.chunk_index for f in result.failures] == [1] and result.chunks_processed == 1


@pytest.mark.parametrize("answer", [{"requirements": "none"}, {"items": []}, "text", 5])
def test_wrong_shaped_answers_count_as_chunk_failures(answer):
    fake = FakeOllama(json_reply(answer), json_reply({"requirements": [req()]}))
    result = ex.extract_requirements(make_chunks(["a " * 100, PAGE_1]), client=make_client(fake))
    assert len(result.failures) == 1 and len(result.items) == 1


def test_if_no_chunk_gives_a_usable_answer_the_call_fails_loudly():
    fake = FakeOllama(text_reply("nope"), text_reply("still nope"))
    with pytest.raises(OllamaResponseError):
        ex.extract_requirements(make_chunks(["a " * 100, "b " * 100]), client=make_client(fake))


@pytest.mark.parametrize(
    "error", [ConnectionError("x"), TimeoutError("x")], ids=["unavailable", "timeout"]
)
def test_server_problems_abort_at_once_instead_of_retrying_every_chunk(error):
    fake = FakeOllama(error)
    with pytest.raises((OllamaUnavailableError, OllamaTimeoutError)):
        ex.extract_requirements(make_chunks(["a " * 100, "b " * 100]), client=make_client(fake))
    assert len(fake.calls) == 1


def test_missing_model_aborts_with_a_clear_error():
    from tests.ai_helpers import raw_reply
    fake = FakeOllama(raw_reply(404, {"error": "model 'gemma3:4b' not found"}))
    with pytest.raises(OllamaModelNotFoundError):
        ex.extract_deadlines(make_chunks([PAGE_1]), client=make_client(fake))


# --- deadlines ------------------------------------------------------------------------------------
def test_deadline_extraction_requires_the_value_inside_the_quotation():
    ok = {"label": "Bid submission deadline", "value": "15 March 2026 at 12:00 noon",
          "normalized_value": "2026-03-15", "quotation": DUE}
    unsupported = {**ok, "label": "Other", "value": "1 June 2026"}
    no_year = {**ok, "label": "Third", "normalized_value": "2027-03-15"}
    fake = FakeOllama(json_reply({"deadlines": [ok, unsupported, no_year]}))
    result = ex.extract_deadlines(make_chunks([PAGE_1]), client=make_client(fake))

    first, second = result.items
    assert first.normalized_value == "2026-03-15" and first.quote_verified and first.page_number == 1
    assert second.normalized_value is None  # year 2027 is not in the source wording
    assert len(result.rejected) == 1 and "not supported" in result.rejected[0].reason
    assert result.prompt == "extract_deadlines_v1"


def test_deadline_without_a_complete_date_keeps_the_text_only():
    fake = FakeOllama(json_reply({"deadlines": [{
        "label": "Completion", "value": "within 18 months of award", "normalized_value": None,
        "quotation": "Works shall be completed within 18 months of award of contract."}]}))
    (item,) = ex.extract_deadlines(make_chunks(["Works shall be completed within 18 months of award of contract."]),
                                   client=make_client(fake)).items
    assert item.value == "within 18 months of award" and item.normalized_value is None


# --- risks -----------------------------------------------------------------------------------------
def test_risks_carry_no_rating_or_score():
    fake = FakeOllama(json_reply({"risks": [{
        "title": "Delay damages", "description": "0.5% per week", "category": "weird",
        "quotation": PAGE_2, "probability": 5, "impact": 5, "score": 25}]}))
    (risk,) = ex.extract_risks(make_chunks([PAGE_2]), client=make_client(fake)).items
    values = risk.to_risk_values()
    assert risk.category is RiskCategory.OTHER
    assert not {"probability", "impact", "score"} & set(values)
    assert values["verification_status"] is VerificationStatus.REQUIRES_REVIEW


# --- compatibility with the real models -------------------------------------------------------------
def test_values_can_be_stored_in_the_existing_models(session):
    company = Company(name="Acme")
    session.add(company)
    session.flush()
    project = Project(company_id=company.id, name="Steel Factory")
    session.add(project)
    session.flush()
    doc = Document(project_id=project.id, original_filename="tender.pdf", storage_path="uploads/t.pdf")
    session.add(doc)
    session.flush()

    fake = FakeOllama(
        json_reply({"requirements": [req(deadline_text="15 March 2026", deadline="2026-03-15", quotation=PAGE_1)]}),
        json_reply({"deadlines": [{"label": "Bid deadline", "value": "15 March 2026", "normalized_value": "2026-03-15", "quotation": DUE}]}),
        json_reply({"risks": [{"title": "Delay", "category": "schedule", "quotation": CERT}]}),
    )
    client = make_client(fake)
    chunks = make_chunks([PAGE_1])
    requirement = ex.extract_requirements(chunks, client=client).items[0]
    fact = ex.extract_deadlines(chunks, client=client).items[0]
    risk = ex.extract_risks(chunks, client=client).items[0]

    session.add_all([
        Requirement(project_id=project.id, code="REQ-001", source_document_id=doc.id, **requirement.to_requirement_values()),
        ExtractedFact(document_id=doc.id, **fact.to_fact_values()),
        Risk(project_id=project.id, code="RISK-001", source_document_id=doc.id, **risk.to_risk_values()),
    ])
    session.flush()
    stored = session.query(Requirement).one()
    assert stored.verification_status is VerificationStatus.REQUIRES_REVIEW and stored.quote_verified is True
    assert stored.deadline == datetime(2026, 3, 15, tzinfo=timezone.utc)
    assert session.query(ExtractedFact).one().fact_type is FactType.DATE
    assert session.query(Risk).one().extractor == "extract_risks_v1@gemma3:4b"
