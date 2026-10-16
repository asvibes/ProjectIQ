# ProjectIQ Prompts

> **Status: design only.** The four prompt files in `backend/app/services/ai/prompts/` and the AI service modules are currently empty, and no Ollama integration exists. This document defines the conventions and the intended behaviour so implementations can be built and evaluated consistently. Replace "intended" with real prompt text, versions and results as they are written.

## 1. Conventions

- **Location**: `backend/app/services/ai/prompts/<task>_v<N>.txt`, one task per file.
- **Versioning**: a prompt is immutable once used on real data. Any change to wording, schema or examples creates a new file (`..._v2.txt`). The old version stays so earlier results remain explainable.
- **Provenance**: the name of the prompt (and model) is stored with every result in the `extractor` column of `requirements` and `extracted_facts` (for example `extract_requirements_v1`). The column is a 120-character string.
- **Local model**: prompts target Gemma served by Ollama. Model name and sampling settings are to be recorded with each prompt version once implemented (currently no setting exists in `config.py`).
- **Document text is data**: tender text is inserted inside clearly delimited blocks, and every prompt states that anything inside the block is quoted material, never instructions (see [SECURITY_PRIVACY.md](SECURITY_PRIVACY.md)).
- **Structured output**: extraction prompts return strict JSON that the schema validator checks before anything is stored.

## 2. Shared input format

Input text comes from the ingestion layer's `ExtractedDocument.to_marked_text()` (implemented), which inserts markers so the model can cite locations:

```
[Page 3]
4.2 The Contractor shall hold ISO 9001 certification ...

[Sheet: BOQ]
Item 14 | Structural steel, Grade S355 | 120 | tonnes
```

Long documents are split by the chunker (planned) so that each chunk keeps its page/sheet markers.

## 3. Shared output rules (all extraction prompts)

Each returned item must include:

| Field | Rule |
|---|---|
| `quotation` | Verbatim text copied from the source; required and non-empty |
| `page_number` / `location_ref` | Where the quotation appears, taken from the markers; `null` if not determinable |
| value fields | As written in the source; the model must not infer, convert or fill gaps |
| `is_mandatory` and similar flags | `null` when the source does not say |

If the document does not contain the information, the correct output is an empty list, not a guess. The model never assigns `Verified` status; stored items start as `Requires review`.

After generation, deterministic code (planned) rejects the response if it fails the schema, and flags any item whose quotation cannot be found in the source (`quote_verified = false`).

## 4. Prompt catalogue

| Prompt file | Intended purpose | Output feeds | Status |
|---|---|---|---|
| `extract_requirements_v1.txt` | Extract tender requirements: description, category (the `RequirementCategory` values), mandatory flag, deadline, quotation, location | `requirements` | Empty; `extract_requirements_v1` is the example name used in the schema |
| `extract_deadlines_v1.txt` | Extract dates and deadlines (submission, clarification, completion, milestones) | `extracted_facts` (type `date`), `requirements.deadline` | Empty |
| `extract_risks_v1.txt` | Surface risk-bearing clauses (penalties, liquidated damages, payment terms, unusual conditions) with quotations | Risk register (model not yet defined) | Empty |
| `briefing_v1.txt` | Draft the decision briefing from already-extracted, human-reviewed data | Briefing view / exports | Empty |

Planned AI modules that will use them: `extractor.py` (the three extraction prompts), `drafter.py` (briefing and other drafts), `explainer.py` (explain a finding in plain language), `qa.py` (answer project questions with citations), all through `ollama_client.py`.

### Intended behaviour of `briefing_v1`

The briefing prompt receives structured data, not raw documents: verified requirements, match results and gaps, deterministic financial results and risks. It must (a) only state things present in that input, (b) cite requirement codes or fact IDs for each claim, (c) say plainly when something is Unknown, Conflicting or unverified, and (d) present a recommendation as decision support for a person, never as a decision. All numbers are copied from the finance modules and are not computed by the model.

## 5. Evaluation approach (planned)

Files reserved: `eval/run_eval.py`, `eval/EVAL_NOTES.md`, and `demo-data/` (a synthetic steel-factory tender with addendum, bill of quantities, and company documents, plus `answer_key.md`). All are currently empty.

Intended method:

1. **Answer key**: for each demo document, a hand-written list of expected requirements and facts with their quotations and locations.
2. **Run**: execute each prompt version over the demo set with fixed model and settings.
3. **Metrics** per prompt version:
   - recall and precision of extracted requirements against the key;
   - **quote-verification rate**: share of returned quotations found in the source (target 100% for items that are stored as extracted);
   - schema-validity rate of model output;
   - unsupported-value rate: values not backed by the quotation;
   - handling of "not stated" cases (empty list, `null` flags);
   - conflict detection on the addendum (for example a changed deadline).
4. **Injection set**: documents containing instructions aimed at the model (see `tests/test_prompt_injection.py`, currently empty); the pass condition is that the output is unchanged and no instruction is followed.
5. **Regression rule**: a new prompt version is adopted only if it does not reduce quote-verification rate and does not lose requirements the previous version found, and results are recorded in `eval/EVAL_NOTES.md`.

Because small local models vary between runs, results should be reported over several runs rather than a single run.