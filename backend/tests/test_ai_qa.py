"""qa: grounding, citation verification and failure handling (Ollama mocked)."""
from types import SimpleNamespace

import pytest

from app.services.ai import qa
from app.services.ai.ollama_client import OllamaResponseError, OllamaUnavailableError
from app.services.errors import ServiceError
from tests.ai_helpers import FakeOllama, json_reply, make_chunks, make_client, text_reply

TURNOVER = "The bidder must have an average annual turnover of at least USD 12,500,000 over the last three years."
DEADLINE = "Bids must be submitted by 15 March 2026 at 12:00 noon."


def passages():
    return [
        qa.EvidencePassage(TURNOVER, source_filename="tender.pdf", page_number=4, location_ref="page 4",
                           document_id=7, verification_status="Requires review"),
        qa.EvidencePassage(DEADLINE, source_filename="tender.pdf", page_number=2, location_ref="page 2", document_id=7),
        qa.EvidencePassage("The site is located near the harbour.", source_filename="site.docx"),
    ]


def answered(answer, *citations, status="answered"):
    return json_reply({"answer_status": status, "answer": answer,
                       "citations": [{"evidence_id": i, "quotation": q} for i, q in citations]})


def ask(question, reply, evidence=None, **kw):
    fake = FakeOllama(reply)
    result = qa.answer_question(question, passages() if evidence is None else evidence, client=make_client(fake), **kw)
    return result, fake


def test_answer_with_verified_citation_takes_location_from_the_supplied_passage():
    reply = json_reply({
        "answer_status": "answered",
        "answer": "The bidder needs an average annual turnover of at least USD 12,500,000. This has not been confirmed yet.",
        "citations": [{"evidence_id": "E1", "quotation": "average annual turnover of at least USD 12,500,000",
                       "page_number": 99, "source_filename": "invented.pdf"}],
    })
    result, fake = ask("What annual turnover is required?", reply)
    assert result.status is qa.QAStatus.ANSWERED and "12,500,000" in result.answer
    (citation,) = result.citations
    assert (citation.source_filename, citation.page_number, citation.location_ref, citation.document_id) == ("tender.pdf", 4, "page 4", 7)
    assert citation.verification_status == "Requires review"
    assert not result.is_confirmed and result.dropped_citations == 0
    assert result.generated_by == "qa_v1@gemma3:4b" and result.passages_used == 1  # only the relevant passage was sent


def test_prompt_fences_question_and_evidence_and_states_the_rules():
    _, fake = ask("What annual turnover is required?",
                  answered("USD 12,500,000.", ("E1", "annual turnover of at least USD 12,500,000")))
    prompt, system = fake.prompts[0], fake.systems[0]
    assert "<<<BEGIN UNTRUSTED QUESTION" in prompt and "<<<BEGIN UNTRUSTED EVIDENCE E1" in prompt
    assert prompt.count("<<<END UNTRUSTED") == 2
    assert '"review_status": "Requires review"' in prompt and '"location": "page 4"' in prompt
    assert "ONLY" in system and "insufficient_evidence" in system
    assert fake.calls[0]["payload"]["format"] == "json"


def test_model_saying_the_evidence_is_insufficient_gives_not_found():
    result, _ = ask("What annual turnover is required?", answered("I do not know", status="insufficient_evidence"))
    assert result.status is qa.QAStatus.NOT_FOUND and result.answer == qa.NOT_FOUND_TEXT and result.citations == ()


def test_no_relevant_evidence_means_no_model_call():
    fake = FakeOllama()
    result = qa.answer_question("What is the penalty for late delivery?", passages(), client=make_client(fake))
    assert result.status is qa.QAStatus.NOT_FOUND and fake.calls == [] and result.passages_used == 0
    assert qa.answer_question("anything about turnover?", [], client=make_client(fake)).status is qa.QAStatus.NOT_FOUND


def test_invalid_citations_are_dropped_and_valid_ones_kept():
    reply = answered("Turnover of USD 12,500,000 is required.",
                     ("E1", "annual turnover of at least USD 12,500,000"),
                     ("E9", "annual turnover of at least USD 12,500,000"),  # no such passage
                     ("E1", "a quotation the passage never contained"),  # not in the passage
                     ("E1", "short"))  # too short to prove anything
    result, _ = ask("What annual turnover is required?", reply)
    assert result.status is qa.QAStatus.ANSWERED and len(result.citations) == 1
    assert result.dropped_citations == 3 and any("3 citation" in w for w in result.warnings)


def test_answer_whose_citations_all_fail_is_withheld():
    result, _ = ask("What annual turnover is required?", answered("Turnover is USD 12,500,000.", ("E1", "this text is not in the evidence")))
    assert result.status is qa.QAStatus.UNSUPPORTED and result.answer == qa.UNSUPPORTED_TEXT
    assert result.citations == () and result.dropped_citations == 1
    assert "12,500,000" not in result.answer


def test_answer_with_a_figure_not_in_the_evidence_is_withheld():
    reply = answered("The required turnover is USD 15,000,000.", ("E1", "average annual turnover of at least USD 12,500,000"))
    result, _ = ask("What annual turnover is required?", reply)
    assert result.status is qa.QAStatus.UNSUPPORTED and any("figures" in w for w in result.warnings)


def test_figures_from_the_question_are_allowed_in_the_answer():
    reply = answered("Yes, USD 12,500,000 is the minimum.", ("E1", "annual turnover of at least USD 12,500,000"))
    result, _ = ask("Is USD 12,500,000 the minimum turnover?", reply)
    assert result.status is qa.QAStatus.ANSWERED


def test_verified_evidence_makes_the_answer_confirmed():
    evidence = [qa.EvidencePassage(DEADLINE, source_filename="t.pdf", verification_status="Verified")]
    result, _ = ask("When must bids be submitted?", answered("15 March 2026.", ("E1", "submitted by 15 March 2026")), evidence)
    assert result.status is qa.QAStatus.ANSWERED and result.is_confirmed


@pytest.mark.parametrize(
    "reply",
    [text_reply("not json"), json_reply(["a"]), json_reply({"answer_status": "maybe", "answer": "x"}),
     json_reply({"answer_status": "answered", "answer": "", "citations": []}),
     json_reply({"answer_status": "answered", "answer": "x" * 5000, "citations": []}),
     json_reply({"answer_status": "answered", "answer": 5})],
)
def test_malformed_model_output_raises_a_response_error(reply):
    with pytest.raises(OllamaResponseError):
        ask("What annual turnover is required?", reply)


def test_missing_citations_field_is_unsupported_not_a_crash():
    result, _ = ask("What annual turnover is required?", json_reply({"answer_status": "answered", "answer": "Some answer."}))
    assert result.status is qa.QAStatus.UNSUPPORTED


def test_unavailable_model_propagates():
    with pytest.raises(OllamaUnavailableError):
        ask("What annual turnover is required?", ConnectionError("x"))


@pytest.mark.parametrize("question,limit", [("", None), ("   ", None), ("q " * 3000, "longer")])
def test_bad_questions_are_422(question, limit):
    with pytest.raises(ServiceError) as info:
        qa.answer_question(question, passages(), client=make_client(FakeOllama()))
    assert info.value.status_code == 422


# --- selecting passages ----------------------------------------------------------------------
def test_select_passages_ranks_by_overlap_and_respects_budget():
    ps = [qa.EvidencePassage("harbour cranes"), qa.EvidencePassage("turnover turnover bid"),
          qa.EvidencePassage("annual turnover bid deadline")]
    picked = qa.select_passages("What is the annual turnover and bid deadline?", ps)
    assert [p.text for p in picked] == ["annual turnover bid deadline", "turnover turnover bid"]
    assert qa.select_passages("unrelated topic xyz", ps) == []
    assert len(qa.select_passages("turnover", ps * 10, max_passages=3)) == 3
    big = [qa.EvidencePassage("turnover " + "x" * 3000) for _ in range(6)]
    assert len(qa.select_passages("turnover", big, max_chars=7000)) == 2


def test_select_false_sends_everything_up_to_the_cap():
    result, fake = ask("What annual turnover is required?",
                       answered("USD 12,500,000.", ("E1", "annual turnover of at least USD 12,500,000")), select=False)
    assert result.passages_used == 3 and "EVIDENCE E3" in fake.prompts[0]


def test_long_passages_are_truncated_before_sending_and_quotes_must_be_in_what_was_sent():
    long_passage = qa.EvidencePassage("filler " * 1000 + "the retention is 5 percent of each payment")
    reply = answered("Retention is applied.", ("E1", "the retention is 5 percent of each payment"))
    result, _ = ask("What is the retention?", reply, [long_passage])
    assert result.status is qa.QAStatus.UNSUPPORTED  # that sentence was cut off, so it cannot be cited


# --- building passages ------------------------------------------------------------------------
def test_passage_from_chunk_keeps_chunk_provenance():
    (chunk,) = make_chunks([TURNOVER])
    p = qa.passage_from_chunk(chunk, document_id=3)
    assert (p.source_filename, p.page_number, p.location_ref, p.document_id) == ("tender.pdf", 1, "page 1", 3)
    two_pages = make_chunks([TURNOVER, DEADLINE], max_chars=1000)[0]
    assert qa.passage_from_chunk(two_pages).page_number is None  # spans pages: no single page claimed


def test_passage_from_stored_chunk_row():
    row = SimpleNamespace(text="abc", page_start=2, page_end=2, location_ref="page 2", document_id=5)
    p = qa.passage_from_chunk_row(row, source_filename="t.pdf")
    assert (p.text, p.page_number, p.document_id, p.source_filename) == ("abc", 2, 5, "t.pdf")
    assert qa.passage_from_chunk_row(SimpleNamespace(text="x", page_start=1, page_end=3)).page_number is None
