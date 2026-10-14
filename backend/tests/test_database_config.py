"""Tests for settings, engine setup, table registration and the Pydantic conventions."""
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect, text

from app.config import BACKEND_DIR, Settings
from app.database import Base, create_db_engine, init_db
from app.models import Company
from app.schemas.base import ORMModel, RequestModel

EXPECTED_TABLES = {
    "companies",
    "company_workforce_roles",
    "company_equipment",
    "company_certifications",
    "company_past_projects",
    "projects",
    "documents",
    "requirements",
    "extracted_facts",
}


def clean_settings(monkeypatch, **env):
    for key in ("DATABASE_URL", "STORAGE_DIR", "SQL_ECHO", "DEFAULT_CURRENCY", "APP_ENV"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


def test_default_database_path_is_backend_storage(monkeypatch):
    s = clean_settings(monkeypatch)
    assert s.database_url == f"sqlite:///{(BACKEND_DIR / 'storage' / 'projectiq.db').as_posix()}"
    assert s.uploads_dir == BACKEND_DIR / "storage" / "uploads"
    assert s.generated_dir == BACKEND_DIR / "storage" / "generated"


def test_env_overrides_and_relative_paths(monkeypatch):
    s = clean_settings(monkeypatch, DATABASE_URL="sqlite:///./storage/other.db", SQL_ECHO="true")
    assert s.sql_echo is True
    assert s.database_url == f"sqlite:///{(BACKEND_DIR / 'storage' / 'other.db').as_posix()}"
    assert clean_settings(monkeypatch, DATABASE_URL="sqlite://").database_url == "sqlite://"


def test_invalid_settings_rejected(monkeypatch):
    with pytest.raises(ValidationError):
        clean_settings(monkeypatch, DEFAULT_CURRENCY="DOLLARS")
    with pytest.raises(ValidationError):
        clean_settings(monkeypatch, APP_ENV="staging")


def test_ensure_storage_dirs(monkeypatch, tmp_path):
    s = clean_settings(monkeypatch, STORAGE_DIR=str(tmp_path / "store"))
    s.ensure_storage_dirs()
    assert (tmp_path / "store" / "uploads").is_dir() and (tmp_path / "store" / "generated").is_dir()


def test_init_db_registers_all_models(engine):
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES <= set(Base.metadata.tables)


def test_init_db_is_idempotent(engine):
    init_db(engine)  # second call must not fail
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())


def test_file_database_created_with_foreign_keys_on(tmp_path):
    path = tmp_path / "nested" / "test.db"
    path.parent.mkdir()
    eng = create_db_engine(f"sqlite:///{path.as_posix()}")
    init_db(eng)
    with eng.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
    assert path.exists()
    eng.dispose()


def test_orm_model_reads_sqlalchemy_objects(session):
    class CompanyRead(ORMModel):
        id: int
        name: str
        currency: str

    c = Company(name="Acme")
    session.add(c)
    session.commit()
    out = CompanyRead.model_validate(c)
    assert (out.name, out.currency) == ("Acme", "USD")


def test_request_model_rejects_unknown_fields():
    class NewCompany(RequestModel):
        name: str

    assert NewCompany(name="  Acme ").name == "Acme"
    with pytest.raises(ValidationError):
        NewCompany(name="Acme", nmae="typo")


def test_cli_init_creates_tables(tmp_path):
    """`python -m app.database` must create tables (regression: __main__ vs app.database Base)."""
    import os
    import sqlite3
    import subprocess
    import sys

    env = {**os.environ, "STORAGE_DIR": str(tmp_path / "store")}
    env.pop("DATABASE_URL", None)
    result = subprocess.run(
        [sys.executable, "-m", "app.database"], cwd=BACKEND_DIR, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    db = tmp_path / "store" / "projectiq.db"
    tables = {r[0] for r in sqlite3.connect(db).execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED_TABLES <= tables
