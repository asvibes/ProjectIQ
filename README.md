# ProjectIQ

**AI-assisted tender evaluation and bid/no-bid decision support for industrial construction and engineering contractors.**

ProjectIQ helps a contractor answer one question with evidence: *should we bid on this tender?* It reads tender documents, extracts requirements together with the exact quotation that supports each one, compares them against what the company can actually prove it has, and prepares a decision briefing. It is **decision support only**. A person reviews every uncertain or conflicting finding, and nothing extracted by AI is treated as verified until a person confirms it.

> **Project status: early development (backend foundation only).**
> The data model, configuration, application shell and text sanitiser are implemented and tested.
> Everything else described below, including document parsing, AI extraction, matching, finance, risk, scenarios, briefings, exports and the entire frontend, is **planned**: the files exist as empty placeholders. See [Implementation status](#implementation-status) for the exact picture.

---

## Vision

| Capability | Purpose |
|---|---|
| Company profile and capability management | Workforce roles, equipment, certifications, past projects and finances, each fact carrying a verification status and date |
| Tender document ingestion | Read PDF, DOCX, XLSX and text tenders without altering the originals |
| Evidence-grounded requirement extraction | Every extracted requirement or fact must carry a supporting quotation and its location in the source |
| Company-tender matching and gap analysis | Compare each requirement with company evidence; `Unknown` is the default and is never upgraded on keyword overlap |
| Financial feasibility, bid pricing, cash flow | Deterministic calculations (not LLM-generated numbers) |
| Risk identification and assessment | Surface and score risks from the tender and the company's position |
| Scenario comparison | Compare alternative bids and assumptions side by side |
| Evidence-backed decision briefings | A summary whose claims trace back to sources |
| Local AI processing | Gemma through Ollama, so tender documents stay on the user's machine |
| Human verification | Uncertain or conflicting findings are routed to a person |

The MVP/future split is defined in [docs/PRD.md](docs/PRD.md).

## Implementation status

| Area | State |
|---|---|
| Configuration (`app/config.py`) | Implemented, tested |
| Database engine, SQLite foreign keys, `init_db` | Implemented, tested |
| ORM models: Company (+ workforce, equipment, certifications, past projects), Project, Document, Requirement, ExtractedFact | Implemented, tested |
| FastAPI app factory, `/health`, CORS, router auto-discovery | Implemented, tested |
| Ingestion: text sanitiser, size and zip-bomb checks, shared result types | Implemented (**no dedicated tests yet**) |
| Ingestion: PDF / DOCX / XLSX / text readers, chunker | Placeholders (empty files) |
| API routers (companies, projects, documents, requirements, fit, financials, risks, scenarios, briefing, chat, reports, resources, settings) | Placeholders; only `GET /health` exists |
| AI layer (Ollama client, extractor, explainer, drafter, Q&A, prompts) | Placeholders; no Ollama code yet |
| Analysis (matcher, gap detector, workforce gap, equipment options, risk scoring) | Placeholders |
| Finance (cost model, bid pricing, break-even, cash flow, scenarios) | Placeholders |
| Verification (quote checker, contradiction, schema validator) | Placeholders |
| Models for risks, scenarios, financial models, resources, artifacts, audit | Placeholders; no schema yet |
| Export (CSV, DOCX, PPTX) | Placeholders |
| Frontend (React pages, components, charts) | Placeholders; `package.json` is empty |
| Docker Compose, PowerShell setup scripts | Placeholders (empty) |
| Demo data and evaluation harness (`demo-data/`, `eval/`) | Placeholders (empty) |

Current test suite: **59 passing** (`backend/tests/`).

## Technology stack

**In use today**

- Python 3 (developed and tested on 3.13; no minimum version is declared yet)
- FastAPI and Uvicorn
- SQLAlchemy 2.0 with SQLite (local default; the code avoids SQLite-only assumptions where practical)
- Pydantic 2 and pydantic-settings
- pytest and httpx

**Planned (not yet wired up)**

- Gemma served locally by Ollama
- PDF, DOCX and XLSX parsing libraries (none are in `requirements.txt` yet)
- React + TypeScript + Vite + Tailwind frontend (file layout exists; no dependencies declared)
- Docker Compose and Windows PowerShell setup scripts
- Alembic migrations (the schema is currently created with `create_all`)

## Prerequisites

- Python 3.13 recommended (the version the tests were run on)
- `pip` and the `venv` module
- Nothing else is needed to run the backend and tests today. Ollama, a Gemma model and Node.js will only be required once the AI layer and frontend exist.

## Installation

```bash
git clone https://github.com/asvibes/ProjectIQ.git
cd ProjectIQ/backend

python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configuration

The backend runs with no configuration. To override defaults, copy `.env.example` to `.env` in the repo root or in `backend/` (the `backend/` file wins). Never commit `.env`.

| Variable | Default | Meaning |
|---|---|---|
| `APP_ENV` | `development` | `development`, `test` or `production` |
| `STORAGE_DIR` | `backend/storage` | Root for uploads, generated files and the SQLite file. Relative paths resolve against `backend/` |
| `DATABASE_URL` | `sqlite:///<STORAGE_DIR>/projectiq.db` | SQLAlchemy URL. Relative SQLite paths resolve against `backend/` |
| `SQL_ECHO` | `false` | Log every SQL statement (can expose data in logs) |
| `DEFAULT_CURRENCY` | `USD` | ISO 4217 code used when a company or project has none |

## Running

From `backend/`:

```bash
uvicorn app.main:app --reload
```

- Liveness check: <http://127.0.0.1:8000/health>
- Interactive API docs: <http://127.0.0.1:8000/docs>

Tables are created automatically at startup. To create them without starting the server:

```bash
python -m app.database
```

At present `/health` is the only endpoint. The CORS allowlist covers `localhost` and `127.0.0.1` on ports 5173 and 3000 (intended for the future frontend).

## Running the tests

From `backend/`:

```bash
pytest
```

Tests use an in-memory SQLite database and never touch `backend/storage/projectiq.db`.

## Project layout

```
backend/
  app/
    main.py            # app factory, /health, CORS, router mounting
    config.py          # settings (env + optional .env)
    database.py        # engine, sessions, init_db
    models/            # SQLAlchemy models (core models implemented; 6 placeholder files)
    routers/           # auto-discovered API routers (all placeholders)
    schemas/base.py    # Pydantic base classes (ORMModel, RequestModel)
    services/          # ingestion, ai, analysis, finance, verification, export
  tests/
frontend/              # planned React app (placeholders)
docs/                  # documentation
demo-data/  eval/  scripts/  docker-compose.yml   # placeholders
```

## Documentation

| Document | Contents |
|---|---|
| [docs/PRD.md](docs/PRD.md) | Product vision, users, requirements, workflows, MVP vs future scope |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, data flow, AI integration, implemented vs planned |
| [docs/DATABASE.md](docs/DATABASE.md) | Tables, relationships, constraints and conventions |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Developer workflow and coding conventions |
| [docs/PROMPTS.md](docs/PROMPTS.md) | Prompt conventions and planned prompts |
| [docs/SECURITY_PRIVACY.md](docs/SECURITY_PRIVACY.md) | Data handling, threat model, current limitations |

## Disclaimer

ProjectIQ supports human decision-making. It does not give legal, financial or contractual advice, and its outputs must be checked against the source documents before any bid decision.

## License

No license has been chosen yet: the `LICENSE` file is currently empty. Until one is added, all rights are reserved by the author.