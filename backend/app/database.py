"""Database engine, session factory and the shared declarative ``Base``.

SQLite is the local default. ``PRAGMA foreign_keys=ON`` is enabled on every SQLite
connection because SQLite ignores foreign keys (and ON DELETE rules) otherwise.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Optional

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings

# Predictable constraint names make future Alembic migrations and error messages sane.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def create_db_engine(url: str, echo: bool = False) -> Engine:
    """Build an engine. In-memory SQLite shares one connection so tables persist per engine."""
    parsed = make_url(url)
    is_sqlite = parsed.get_backend_name() == "sqlite"
    kwargs: dict = {"echo": echo}
    if is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False}
        if parsed.database in (None, "", ":memory:"):
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)

    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record) -> None:  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


_settings = get_settings()
engine: Engine = create_db_engine(_settings.database_url, echo=_settings.sql_echo)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(bind: Optional[Engine] = None) -> None:
    """Create all tables. Importing ``app.models`` registers every model on ``Base``."""
    import app.models  # noqa: F401  (side effect: registers tables)

    if bind is None:
        get_settings().ensure_storage_dirs()
    Base.metadata.create_all(bind or engine)


if __name__ == "__main__":  # python -m app.database
    # Run via the canonical module: when executed as __main__ this file is a *second* copy
    # of app.database, and the models (which import app.database.Base) would register on a
    # different Base than the one used here, silently creating no tables.
    from app.database import init_db as _init_db, _settings as _canonical_settings

    _init_db()
    print(f"Database ready: {_canonical_settings.database_url}")
