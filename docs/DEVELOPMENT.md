# Development Guide

For setup and running instructions see the [README](../README.md). This guide covers conventions and workflows that are not obvious from the code.

## Repository layout

| Path | Purpose |
|---|---|
| `backend/app/` | FastAPI application (see [ARCHITECTURE.md](ARCHITECTURE.md)) |
| `backend/tests/` | pytest suite (run from `backend/`) |
| `frontend/` | Planned React app (placeholders only) |
| `docs/` | Documentation |
| `demo-data/`, `eval/` | Planned demo tender and evaluation harness (placeholders) |
| `scripts/`, `docker-compose.yml` | Planned setup tooling (placeholders) |

Many files exist as **empty placeholders** that reserve the planned structure. Check [ARCHITECTURE.md](ARCHITECTURE.md#2-component-status) before assuming a module is implemented.

## Everyday commands

```bash
cd backend
source .venv/bin/activate
pytest                          # all tests
pytest tests/test_models_core.py -k verified   # a subset
uvicorn app.main:app --reload   # dev server on :8000
python -m app.database          # create tables only
```

## Conventions

### Adding an API endpoint group

Create `backend/app/routers/<name>.py` with a module-level `router = APIRouter(prefix="/<name>", tags=["<name>"])`. It is mounted automatically; do not edit `main.py` or `routers/__init__.py`. Routers load in alphabetical order. A broken router fails startup on purpose.

### Schemas

Response schemas inherit `ORMModel` (`from_attributes=True`). Request schemas inherit `RequestModel` (unknown fields are rejected, strings are stripped).

### Adding or changing a model

1. Define the model in `app/models/`, using `TimestampMixin`, `VerifiableMixin`, `SourceLocationMixin` and the helpers in `types.py` (`Money`, `UTCDateTime`, `enum_type`).
2. Import it in `app/models/__init__.py`; `init_db` relies on that import to register tables.
3. Add `verified_requires_date()` to any table that has `VerifiableMixin`.
4. Use `ondelete=` on foreign keys and the matching `cascade` / `passive_deletes` on relationships.
5. Add tests in `tests/test_models_core.py` or a new file.
6. There are no migrations: delete the local SQLite file to pick up schema changes (see [DATABASE.md](DATABASE.md#7-operations-notes)).

### Data rules to preserve

- Unknown is `NULL`/`Unknown`, never a guessed default.
- New facts start as `Requires review`; only a person marks them `Verified`.
- Datetimes must be timezone-aware UTC (`utcnow()`); naive values raise.
- Readers and parsers raise typed `IngestionError` subclasses with a user-presentable message; callers turn them into `Document.mark_failed(...)`.
- Untrusted file content is data: no `eval`/`exec`, no macro or formula execution, no extraction of archives to disk, no following of external links.

### Testing

- `tests/conftest.py` sets `DATABASE_URL=sqlite://` and `APP_ENV=test` **before** importing `app`, so the module-level engine can never point at the real database. Keep that ordering.
- Use the `engine` and `session` fixtures for database tests (fresh in-memory SQLite, foreign keys on).
- Build the app with `create_app(init_database=False)` when you do not need tables.
- Test files for the sanitiser, quote checker, matcher, contradiction detector, finance modules and prompt-injection handling exist but are empty. Add tests alongside any implementation you write.

### Imports

`app/__init__.py` is deliberately import-free, because `app.database` builds an engine at import time. Import from the specific submodule.

## Git

History so far uses conventional-commit style (`feat(backend): ...`). Keep commits small and descriptive.

## Known gaps for contributors

- No license (the `LICENSE` file is empty).
- No linter, formatter or CI configuration.
- No `pyproject.toml`; Python version is not pinned (tests were run on 3.13).
- The sanitiser has no dedicated tests.