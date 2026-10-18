"""explainer: explanations of real analysis outputs, with grounding checks (Ollama mocked)."""
import pytest

from app.services.ai import explainer as exp
from app.services.ai.ollama_client import OllamaResponseError, OllamaTimeoutError
from app.services.analysis.gap_detector import Gap, GapScope, GapType, Severity
from app.services.analysis.requirement_matcher import EvidenceRef, MatchResult
from app.services.analysis.risk_scoring import assess_risk
from app.models import MatchStatus
from tests.ai_helpers import FakeOllama, json_reply, make_client, text_reply

SOURCE = {"requirement_code": "REQ-004", "document_id": 7, "page_number": 4, "location_ref": "page 4",
          "quotation": "Bidder shall hold ISO 14001:2015.", "quote_verified": True}


def gap(**kw):
    base = dict(
        gap_id="GAP-REQ-004-1", gap_type=GapType.MISSING_INFORMATION, severity=Severity.HIGH, scope=GapScope.REQUIREMENT,
        title="No ISO 14001 certificate on record", detail="The profile lists no certificate for ISO 14001:2015.",
        blocking=True, requirement_code="REQ-004", requirement_text="Bidder shall hold ISO 14001:2015.",
        match_status="Unknown", is_mandatory=True, what_would_close_it="Add the ISO 14001 certificate to the profile.",
        sources=(SOURCE,), requirement_reviewed=True,
    )
    return Gap(**{**base, **kw})


def explanation(**kw):
    return json_reply({"summary": "REQ-004 asks for ISO 14001:2015 and the profile has no such certificate.",
                       "key_points": ["The gap is marked high and blocking."],
                       "next_steps": ["Add the ISO 14001 certificate to the profile."], **kw})


def run(fn, finding, reply, **kw):
    fake = FakeOllama(reply)
    return fn(finding, client=make_client(fake), **kw), fake


def test_gap_explanation_copies_sources_from_the_finding_not_the_model():
    result, fake = run(exp.explain_gap, gap(), explanation(sources=[{"document_id": 999, "page_number": 1}]))
    assert result.kind is exp.FindingKind.GAP and result.subject == "GAP-REQ-004-1"
    assert "ISO 14001:2015" in result.summary and result.key_points == ("The gap is marked high and blocking.",)
    assert result.next_steps == ("Add the ISO 14001 certificate to the profile.",)
    assert result.sources == (SOURCE,)  # exactly what the gap carried
    assert result.generated_by == "explain_v1@gemma3:4b" and result.prompt == "explain_v1"
    prompt = fake.prompts[0]
    assert "<<<BEGIN UNTRUSTED FINDING" in prompt and "GAP-REQ-004-1" in prompt
    assert "Never change" in fake.systems[0]


def test_only_whitelisted_fields_reach_the_model():
    finding = {**gap().to_dict(), "internal_notes": "SECRET-TOKEN", "has_source": True}
    _, fake = run(exp.explain_gap, finding, explanation())
    assert "SECRET-TOKEN" not in fake.prompts[0] and "has_source" not in fake.prompts[0]


def test_long_text_is_clipped():
    _, fake = run(exp.explain_gap, gap(detail="word " * 2000), explanation())
    assert "[truncated]" in fake.prompts[0] and len(fake.prompts[0]) < 10_000


def test_match_result_with_requirement_and_generated_caveats():
    result_obj = MatchResult(
        requirement_id=4, requirement_code="REQ-004", status=MatchStatus.UNKNOWN, rule="certification",
        evidence_summary="Certificate ISO 14001:2015 recorded.", missing_evidence="Verified copy of the certificate.",
        provisional_status=MatchStatus.MET, needs_verification=True,
        evidence=(EvidenceRef("certification", 12, "ISO 14001:2015", "Requires review"),),
    )
    result, fake = run(exp.explain_match, result_obj, explanation(), requirement={
        "code": "REQ-004", "description": "ISO 14001:2015 certificate", "quotation": SOURCE["quotation"], "ignored": 1})
    assert result.kind is exp.FindingKind.MATCH and result.subject == "REQ-004"
    assert result.evidence == ({"kind": "certification", "record_id": 12, "label": "ISO 14001:2015",
                                "verification_status": "Requires review"},)
    assert any("not verified" in c for c in result.caveats)  # generated from needs_verification, not by the model
    assert '"requirement"' in fake.prompts[0] and "ignored" not in fake.prompts[0]


def test_conflict_and_unreviewed_flags_become_caveats():
    result, _ = run(exp.explain_gap, gap(requirement_reviewed=False), explanation())
    assert any("not been reviewed" in c for c in result.caveats)
    fake = FakeOllama(json_reply({"summary": "The records for this requirement conflict."}))
    result = exp.explain_finding(
        "match", {"requirement_code": "REQ-1", "status": "Unknown", "conflict": True}, client=make_client(fake)
    )
    assert any("conflict" in c for c in result.caveats)


def test_risk_explanation_uses_the_scoring_output_and_notes_unassessed_risks():
    assessment = assess_risk({"code": "RISK-002", "title": "Late payment", "probability": 4, "impact": 5, "score": 20,
                              "verification_status": "Verified", "status": "identified"})
    reply = json_reply({"summary": "RISK-002 is rated 20, which is in the Critical band.", "key_points": [], "next_steps": []})
    result, _ = run(exp.explain_risk, assessment, reply)
    assert result.subject == "RISK-002" and result.caveats == () and result.next_steps == ()

    unassessed = assess_risk({"code": "RISK-003", "title": "Weather", "verification_status": "Verified"})
    result, _ = run(exp.explain_risk, unassessed, json_reply({"summary": "RISK-003 has not been assessed."}))
    assert any("not been assessed" in c for c in result.caveats)


def test_invented_figures_are_rejected():
    with pytest.raises(OllamaResponseError) as info:
        run(exp.explain_gap, gap(), explanation(summary="REQ-004 needs ISO 14001:2015 and a 250 million guarantee."))
    assert "figures" in info.value.message


@pytest.mark.parametrize(
    "reply",
    [text_reply("plain prose"), json_reply([]), json_reply({"summary": ""}), json_reply({"key_points": ["x"]}),
     json_reply({"summary": "s" * 1600}), json_reply({"summary": "ok", "key_points": ["k"] * 9}),
     json_reply({"summary": "ok", "next_steps": ["n" * 501]})],
)
def test_malformed_explanations_raise(reply):
    with pytest.raises(OllamaResponseError):
        run(exp.explain_gap, gap(), reply)


def test_status_fields_in_the_model_output_are_ignored():
    result, _ = run(exp.explain_gap, gap(), explanation(severity="low", status="Met", blocking=False))
    assert not hasattr(result, "severity") and not hasattr(result, "status")


def test_bad_inputs_and_server_errors():
    with pytest.raises(TypeError):
        exp.explain_gap(object(), client=make_client(FakeOllama()))
    with pytest.raises(ValueError):
        exp.explain_gap({"unrelated": 1}, client=make_client(FakeOllama()))
    with pytest.raises(ValueError):
        exp.explain_finding("nonsense", {"x": 1}, client=make_client(FakeOllama()))
    with pytest.raises(OllamaTimeoutError):
        run(exp.explain_gap, gap(), TimeoutError("t"))
