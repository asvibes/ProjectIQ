"""drafter: briefing validation, traceability and failure handling (Ollama mocked)."""
from decimal import Decimal

import pytest

from app.models import Artifact, Company, Project, Requirement, RequirementCategory
from app.services.ai import drafter as dr
from app.services.ai.ollama_client import OllamaResponseError, OllamaUnavailableError
from app.services.analysis.gap_detector import Gap, GapScope, GapType, Severity
from app.services.analysis.risk_scoring import assess_risk
from app.services.errors import ServiceError
from tests.ai_helpers import FakeOllama, json_reply, make_client, text_reply


def context(**kw):
    base = dict(
        project={"name": "Steel Factory", "status": "analysing", "currency": "USD", "secret_field": "SECRET-TOKEN"},
        requirements=[
            {"code": "REQ-001", "description": "ISO 9001:2015 certificate", "match_status": "Met",
             "verification_status": "Verified", "quotation": "Bidder shall hold ISO 9001:2015."},
            {"code": "REQ-002", "description": "Turnover of USD 12,500,000", "match_status": "Unknown",
             "verification_status": "Requires review"},
        ],
        gaps=[Gap(gap_id="GAP-REQ-002-1", gap_type=GapType.MISSING_INFORMATION, severity=Severity.HIGH,
                  scope=GapScope.REQUIREMENT, title="Turnover not recorded", detail="No turnover figure on file.",
                  blocking=True, requirement_code="REQ-002", requirement_reviewed=False)],
        risks=[assess_risk({"code": "RISK-001", "title": "Delay damages", "probability": 3, "impact": 4, "score": 12,
                            "verification_status": "Verified", "status": "identified"})],
        facts=[{"id": 5, "label": "Bid deadline", "value": "15 March 2026", "verification_status": "Verified"}],
        financials={"bid_price": "USD 4,250,000", "margin_percent": Decimal("8.5")},
    )
    return dr.BriefingContext(**{**base, **kw})


def draft_json(**kw):
    base = {
        "title": "Steel Factory briefing",
        "sections": [
            {"heading": "Company fit", "body": "REQ-001 is met. REQ-002 is unknown because turnover is not recorded.",
             "references": ["REQ-001", "REQ-002", "GAP-REQ-002-1"]},
            {"heading": "Financial position", "body": "The bid price is USD 4,250,000 with a margin of 8.5.",
             "references": ["FIN-bid_price", "FIN-margin_percent"]},
        ],
        "assumptions": ["The tender deadline will not move."],
        "missing_information": ["Annual turnover for the last three years."],
    }
    return json_reply({**base, **kw})


def run(reply, ctx=None):
    fake = FakeOllama(reply)
    return dr.draft_briefing(ctx or context(), client=make_client(fake)), fake


def test_briefing_with_traceable_sections_and_deterministic_notes():
    briefing, fake = run(draft_json())
    assert [s.heading for s in briefing.sections] == ["Company fit", "Financial position"]
    assert briefing.sections[0].references == ("REQ-001", "REQ-002", "GAP-REQ-002-1")
    assert briefing.assumptions == ("The tender deadline will not move.",)
    assert briefing.missing_information == ("Annual turnover for the last three years.",)
    assert briefing.warnings == () and briefing.generated_by == "briefing_v1@gemma3:4b"
    md = briefing.markdown
    assert md.startswith("# Steel Factory briefing") and "not a bid decision" in md
    assert "Sources: REQ-001, REQ-002, GAP-REQ-002-1" in md
    assert "## Assumptions (not taken from the project data)" in md and "## Missing information" in md
    # REQ-002 is "Requires review" and the gap rests on an unreviewed requirement: the note comes
    # from the supplied data, not from the model
    assert briefing.unverified_references == ("GAP-REQ-002-1", "REQ-002")
    assert "GAP-REQ-002-1, REQ-002." in md.split("Verification note")[1]


def test_payload_is_fenced_whitelisted_and_carries_reference_ids():
    _, fake = run(draft_json())
    prompt = fake.prompts[0]
    assert "<<<BEGIN UNTRUSTED PROJECT DATA" in prompt and "SECRET-TOKEN" not in prompt
    for ref in ("REQ-001", "GAP-REQ-002-1", "RISK-001", "FACT-5", "FIN-bid_price"):
        assert ref in prompt
    assert "8.5" in prompt and "Steel Factory" in prompt
    assert "not making one" in fake.systems[0] and "Never calculate" in fake.systems[0]


def test_unknown_references_are_removed_and_unsupported_sections_dropped():
    reply = draft_json(sections=[
        {"heading": "Fit", "body": "REQ-001 is met.", "references": ["REQ-001", "REQ-777"]},
        {"heading": "Invented", "body": "Something else.", "references": ["REQ-777"]},
        {"heading": "No refs", "body": "Unsupported claim.", "references": []},
        {"heading": "Mentions unknown", "body": "REQ-099 is also met.", "references": ["REQ-001"]},
        {"heading": "Bad figure", "body": "The bid price is USD 9,999,999.", "references": ["FIN-bid_price"]},
        {"heading": "", "body": "no heading", "references": ["REQ-001"]},
    ])
    briefing, _ = run(reply)
    assert [s.heading for s in briefing.sections] == ["Fit"] and briefing.sections[0].references == ("REQ-001",)
    assert any("5 section" in w for w in briefing.warnings)


def test_assumptions_and_missing_lines_with_invented_figures_or_refs_are_removed():
    reply = draft_json(assumptions=["Costs will rise by 27 percent.", "Plain assumption."],
                       missing_information=["See RISK-042.", "Real gap."])
    briefing, _ = run(reply)
    assert briefing.assumptions == ("Plain assumption.",) and briefing.missing_information == ("Real gap.",)
    assert len(briefing.warnings) == 2


def test_title_with_unsupported_figure_falls_back():
    briefing, _ = run(draft_json(title="Bid worth 77 million"))
    assert briefing.title == "Tender decision briefing"


def test_a_draft_with_no_supported_section_is_an_error():
    reply = draft_json(sections=[{"heading": "x", "body": "y", "references": ["NOPE-1"]}])
    with pytest.raises(OllamaResponseError):
        run(reply)


@pytest.mark.parametrize(
    "reply",
    [text_reply("Dear reader, here is a briefing"), json_reply([]), json_reply({"title": "t"}),
     json_reply({"title": "t", "sections": []}), json_reply({"title": "t", "sections": "text"}),
     json_reply({"title": "t", "sections": [{"heading": "h", "body": "b", "references": ["REQ-001"]}] * 13}),
     json_reply({"title": None, "sections": [{"heading": "h", "body": "b", "references": ["REQ-001"]}]})],
)
def test_malformed_drafts_raise(reply):
    with pytest.raises(OllamaResponseError):
        run(reply)


def test_nothing_to_draft_from_is_a_422_and_the_model_is_not_called():
    fake = FakeOllama()
    with pytest.raises(ServiceError) as info:
        dr.draft_briefing(dr.BriefingContext(project={"name": "Only a name"}), client=make_client(fake))
    assert info.value.status_code == 422 and fake.calls == []


def test_items_without_or_with_duplicate_references_are_programming_errors():
    with pytest.raises(ValueError):
        dr.draft_briefing(dr.BriefingContext(requirements=[{"description": "no code"}]), client=make_client(FakeOllama()))
    with pytest.raises(ValueError):
        dr.draft_briefing(dr.BriefingContext(requirements=[{"code": "REQ-1"}, {"code": "REQ-1"}]),
                          client=make_client(FakeOllama()))


def test_large_inputs_are_trimmed_to_the_budget_and_the_model_is_told():
    many = [{"code": f"REQ-{i:03d}", "description": "d" * 300, "verification_status": "Verified"} for i in range(200)]
    briefing, fake = run(
        json_reply({"title": "t", "sections": [{"heading": "h", "body": "REQ-001 exists.", "references": ["REQ-001"]}]}),
        context(requirements=many),
    )
    assert any("did not fit" in w for w in briefing.warnings)
    assert len(fake.prompts[0]) < dr.MAX_PAYLOAD_CHARS + 3000 and '"omitted_items"' in fake.prompts[0]


def test_long_quotations_are_truncated_before_sending():
    ctx = context(requirements=[{"code": "REQ-001", "quotation": "q" * 5000, "verification_status": "Verified"}])
    _, fake = run(draft_json(sections=[{"heading": "h", "body": "REQ-001.", "references": ["REQ-001"]}]), ctx)
    assert "q" * (dr.MAX_QUOTE_CHARS + 1) not in fake.prompts[0]


def test_orm_rows_enums_and_decimals_are_accepted():
    row = Requirement(code="REQ-010", description="Crane", category=RequirementCategory.TECHNICAL,
                      verification_status=None)
    ctx = dr.BriefingContext(requirements=[row], financials={"margin": Decimal("8.50")})
    reply = json_reply({"title": "t", "sections": [{"heading": "h", "body": "REQ-010 is technical.", "references": ["REQ-010"]}]})
    briefing, fake = run(reply, ctx)
    assert '"technical"' in fake.prompts[0] and '"8.50"' in fake.prompts[0]
    assert briefing.unverified_references == ("REQ-010",)  # no status given -> not treated as verified


def test_unavailable_model_propagates():
    with pytest.raises(OllamaUnavailableError):
        run(ConnectionError("x"))


def test_artifact_values_can_be_stored_as_a_briefing(session):
    company = Company(name="Acme")
    session.add(company)
    session.flush()
    project = Project(company_id=company.id, name="Steel Factory")
    session.add(project)
    session.flush()

    briefing, _ = run(draft_json())
    session.add(Artifact(project_id=project.id, **briefing.to_artifact_values()))
    session.flush()
    stored = session.query(Artifact).one()
    assert stored.artifact_type.value == "briefing" and stored.file_format.value == "markdown"
    assert stored.generated_by == "briefing_v1@gemma3:4b" and stored.content == briefing.markdown
    assert stored.extra["status"] == "draft_requires_review" and "REQ-001" in stored.extra["references"]
