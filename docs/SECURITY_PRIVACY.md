# ProjectIQ Security and Privacy

This document separates what the code **does today** from what is **planned**, and lists limitations plainly. ProjectIQ is early-stage, single-user, local software and has not had a security review.

## 1. Data handling

**Today**

- All data lives locally: a SQLite database and an uploads folder under `STORAGE_DIR` (default `backend/storage/`, git-ignored).
- The backend code makes no outbound network calls. There is no telemetry and no cloud AI dependency.
- Original uploaded files are meant to be preserved untouched at `Document.storage_path`; the sanitiser operates on extracted text only, never on the stored file.
- `.env` files are git-ignored (only `.env.example` is tracked). The current settings contain no secrets.
- Company profile data can include commercially sensitive figures (revenue, working capital, bank guarantee limit). These are stored unencrypted in the database.

**Not yet implemented**: upload endpoint, file storage service, deletion/retention tooling, backups, encryption at rest.

## 2. Local AI processing

**Planned**: tender and company text will be sent only to a local Ollama server running Gemma, on the same machine, so documents are not disclosed to a third party. No Ollama code or configuration exists yet. When it is added:

- the Ollama endpoint should default to `localhost` and be configurable, with a visible warning if it points to a non-local host;
- prompts and responses should not be written to logs by default (`SQL_ECHO` and future debug logging can expose document content, so they must stay off in production use).

## 3. File validation (implemented in `services/ingestion/sanitizer.py`)

`load_source` and `ensure_ooxml` validate untrusted input **before** a parser sees it:

| Check | Limit / behaviour |
|---|---|
| File size | Max 50 MiB; larger files raise `ResourceLimitError`. File objects are read with a cap so oversized streams are not fully loaded |
| Extension | Checked against the allowed list for the reader; a mismatch raises `UnsupportedFormatError` |
| Empty file | Rejected as corrupt |
| Legacy/password-protected Office | OLE-signature files are rejected as unsupported |
| Zip structure (DOCX/XLSX) | Must be a valid zip containing the required member (e.g. `word/document.xml`) |
| Zip bomb | Max 5,000 entries; max 500 MiB total uncompressed; compression ratio over 200:1 rejected for entries larger than 1 MiB |
| Path traversal in archive | Entries with absolute paths or `..` are rejected |
| Extraction | Archives are inspected in memory, never extracted to disk |

Every failure raises a typed `IngestionError` whose message is suitable to store via `Document.mark_failed(reason)`.

The text sanitiser removes NUL and other control characters, soft hyphens, zero-width spaces and BOMs; normalises line endings and Unicode spaces; applies NFC; and collapses whitespace. It never uses NFKC for stored text, so numbers, currency symbols and clause numbers are not rewritten. It returns a `SanitizationReport`, and removals of null bytes and control characters surface as warnings, so nothing disappears silently.

Design rules for readers (documented in the module; readers themselves are not written yet): document content is only data, with no `eval`/`exec`, no macro execution, no formula evaluation and no external links followed.

**Limitations of validation today**

- Validation is by extension plus zip structure. There is no content-type sniffing for PDFs or text, and a filename without an extension is accepted.
- The PDF, DOCX, XLSX and text readers do not exist yet, so none of this is connected to an upload path.
- `sha256` is validated when provided, but no code computes it (no duplicate-upload detection).
- There is no filename sanitising or storage-path generation code yet; when written, it must generate paths itself and never trust the client filename.
- No malware scanning.
- **The sanitiser has no automated tests yet.**

## 4. Prompt injection

Tender documents are untrusted: a document can contain text such as "ignore previous instructions". Design position:

- Document text is data. Sanitising removes invisible characters that could hide text, but **sanitising is not a defence against injection**; the real defences are structural.
- The model only *proposes* structured items. Output must pass strict schema validation, and every item needs a quotation that the quote checker finds in the source, so invented or injected content cannot silently enter the evidence base.
- Model output never executes anything and never sets `Verified`; stored items start as `Requires review`.
- Financial figures are computed by deterministic code, not read from model text.
- Planned: delimiter-wrapped document blocks with explicit "treat as data" instructions, and an injection test set (`tests/test_prompt_injection.py` is currently empty).

**Status**: none of these controls is implemented yet except the database rules (mandatory quotation for extracted facts, default `Requires review`).

## 5. Evidence verification

Implemented at the data layer:

- `ExtractedFact` rejects a blank quotation or value.
- A record cannot be `Verified` without `last_verified_at`.
- `quote_verified` records whether a quotation was checked against the source (not checked / passed / failed).
- `match_status` defaults to `Unknown`; it is a separate field from `verification_status`.
- Deleting a source document keeps requirements and their quotations, with the link set to `NULL`, so evidence is not lost silently.

Planned: the quote checker, schema validator and contradiction detector that populate these fields, and a review queue where a person confirms or rejects items. `normalize_for_comparison` (implemented) provides the lossy normal form intended for quote matching and must never be stored.

## 6. Web/API security

- CORS allows only `http://localhost` and `http://127.0.0.1` on ports 5173 and 3000, with credentials allowed.
- **There is no authentication or authorisation.** Anyone who can reach the server can read and change data. Run it on a trusted machine and bind to localhost (Uvicorn's default). Do not expose it to a network.
- SQLAlchemy ORM queries are parameterised; there is no raw SQL string-building in the current code.
- Pydantic request models reject unknown fields (`RequestModel`); no concrete schemas exist yet.

## 7. Known limitations

1. No authentication, users or roles.
2. No encryption at rest; database and uploads are plain files.
3. No upload pipeline, readers, or AI layer yet; most controls above are building blocks, not end-to-end protection.
4. No OCR; scanned PDFs yield "no extractable text".
5. No audit log yet (the model file is a placeholder).
6. Local model output can be wrong; verification and human review are mandatory parts of the workflow, not optional extras.
7. No dependency pinning beyond version ranges and no automated vulnerability scanning.
8. No formal threat model or third-party security review.

## 8. Reporting issues

A reporting contact has not been defined. Until one is added to the README, open a private channel with the maintainer rather than a public issue for any suspected vulnerability.