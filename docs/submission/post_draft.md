# Post Draft

> **Draft.** Written against the repository as it stands today: backend foundation only. Update the "what works" section before publishing, and do not claim anything below the line "What does not exist yet" as done.

---

## Building ProjectIQ: a bid/no-bid assistant that has to show its evidence

Contractors who bid on industrial projects read hundreds of pages of tender documents under time pressure. A missed mandatory requirement, such as a certification, a bonding limit or a changed deadline in an addendum, can waste weeks of bid effort or lock in a loss.

I'm building **ProjectIQ**, an AI-assisted tender evaluation and bid/no-bid decision-support tool for industrial construction and engineering contractors. The idea is simple to say and hard to do well: help a bid team decide, but never ask them to trust the AI on faith.

### Principles

- **Evidence or nothing.** Every extracted requirement must carry the exact quotation that supports it and where it came from. The database refuses an extracted fact without a quotation.
- **Unknown is an answer.** If the company's evidence is missing, the match result is *Unknown*, not a hopeful guess. It is never upgraded because related words appear.
- **Humans verify.** Extracted values start as *Requires review* and become *Verified* only when a person confirms them, with a date.
- **Numbers come from code.** Costing, pricing and cash flow are meant to be deterministic calculations, not text a language model produced.
- **Local first.** The plan is to run Gemma through Ollama on the user's own machine, so confidential tenders are not sent to a third party.

### Where it stands

ProjectIQ is early. What exists and is tested today (59 passing tests):

- The data model for companies (workforce roles, equipment, certifications, past projects, finances), projects, documents, requirements and extracted facts, with database-level rules such as "a failed document must have a reason" and "a Verified record must have a verification date".
- A FastAPI application shell with automatic router discovery and a health check.
- A document text sanitiser with upload safety checks (size limits, zip-bomb and path-traversal checks for DOCX/XLSX).

### What does not exist yet

Document readers, the AI extraction layer and Ollama integration, quote checking, matching and gap analysis, the finance, risk and scenario modules, briefings and exports, and the whole frontend. Those files are placeholders. There is no user feedback yet, and no accuracy numbers, because there is nothing to measure.

### What's next

1. Document readers for PDF, DOCX and XLSX that preserve page and cell locations.
2. Requirement extraction with a quote checker, evaluated against a synthetic demo tender with a hand-written answer key.
3. A review screen where a person confirms or rejects each finding.

Then financial feasibility, risk and scenarios.

If you work in tendering or bid management and would be willing to look at a tender with me once the first workflow runs, I'd like to hear from you.

Repository: https://github.com/asvibes/ProjectIQ

---

## Notes before publishing

- Replace the status section with real results once extraction runs; include the quote-verification rate and the test set used.
- Add a screenshot only of something that exists.
- Add a licence (the `LICENSE` file is currently empty) and a contact line.
- Keep the disclaimer: ProjectIQ is decision support, not legal or financial advice.