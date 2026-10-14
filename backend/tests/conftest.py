"""Shared fixtures. Tests never touch backend/storage/projectiq.db."""
import os

# Must run before any `app` import so the module-level engine can never point at the real DB.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["APP_ENV"] = "test"

import pytest  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import Base, create_db_engine, init_db  # noqa: E402


@pytest.fixture()
def engine():
    """Fresh in-memory SQLite database per test, with foreign keys enforced."""
    eng = create_db_engine("sqlite://")
    init_db(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def session(engine):
    with Session(engine) as s:
        yield s
