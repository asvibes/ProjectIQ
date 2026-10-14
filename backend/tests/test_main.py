"""Tests for application creation, the health check, CORS and router registration."""
from __future__ import annotations

import pathlib
import sys
import textwrap

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app import __version__
from app.main import APP_TITLE, DEFAULT_CORS_ORIGINS, create_app
from app.routers import discover_routers


@pytest.fixture()
def client() -> TestClient:
    # init_database=False: never touch the real SQLite file from a unit test.
    return TestClient(create_app(init_database=False))


# --- application creation -------------------------------------------------------------

def test_create_app_returns_fastapi_with_metadata():
    app = create_app(init_database=False)
    assert isinstance(app, FastAPI)
    assert app.title == APP_TITLE
    assert app.version == __version__


def test_create_app_returns_independent_instances():
    assert create_app(init_database=False) is not create_app(init_database=False)


def test_module_level_app_exists():
    from app.main import app

    assert isinstance(app, FastAPI)


def test_importing_app_package_has_no_side_effects():
    # app/__init__.py must not pull in the database module (it builds an engine on import).
    import importlib

    import app as pkg

    importlib.reload(pkg)
    assert pkg.__version__


# --- health check ---------------------------------------------------------------------

def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["service"] == APP_TITLE
    assert body["environment"] in {"development", "test", "production"}


def test_openapi_lists_health(client):
    assert "/health" in client.get("/openapi.json").json()["paths"]


# --- CORS -----------------------------------------------------------------------------

def test_cors_allows_local_frontend(client):
    origin = DEFAULT_CORS_ORIGINS[0]
    response = client.options(
        "/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_cors_rejects_unknown_origin(client):
    response = client.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_cors_origins_overridable():
    app = create_app(cors_origins=["http://example.test"], init_database=False)
    response = TestClient(app).get("/health", headers={"Origin": "http://example.test"})
    assert response.headers["access-control-allow-origin"] == "http://example.test"


# --- lifespan -------------------------------------------------------------------------

def test_lifespan_initialises_database(monkeypatch):
    import app.database

    calls = []
    monkeypatch.setattr(app.database, "init_db", lambda *a, **k: calls.append(1))
    with TestClient(create_app()):
        pass
    assert calls == [1]


def test_lifespan_skips_database_when_disabled(monkeypatch):
    import app.database

    calls = []
    monkeypatch.setattr(app.database, "init_db", lambda *a, **k: calls.append(1))
    with TestClient(create_app(init_database=False)):
        pass
    assert calls == []


# --- router registration --------------------------------------------------------------

def test_real_router_package_is_discoverable():
    # Must not raise, whether the real router modules are implemented or still empty.
    found = discover_routers()
    assert all(isinstance(r, APIRouter) for _, r in found)
    names = [n for n, _ in found]
    assert names == sorted(names)


def test_app_registers_every_discovered_router():
    app = create_app(init_database=False)
    assert app.state.registered_routers == [n for n, _ in discover_routers()]


@pytest.fixture()
def fake_package(tmp_path, monkeypatch):
    pkg = tmp_path / "fake_routers"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "empty.py").write_text("")  # unimplemented placeholder
    (pkg / "_private.py").write_text("router = 'ignored'")
    (pkg / "alpha.py").write_text(
        textwrap.dedent(
            """
            from fastapi import APIRouter
            router = APIRouter(prefix="/alpha")
            @router.get("/ping")
            def ping():
                return {"ok": "alpha"}
            """
        )
    )
    (pkg / "beta.py").write_text(
        textwrap.dedent(
            """
            from fastapi import APIRouter
            router = APIRouter(prefix="/beta")
            @router.get("/ping")
            def ping():
                return {"ok": "beta"}
            """
        )
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib

    module = importlib.import_module("fake_routers")
    yield module
    for name in [m for m in sys.modules if m == "fake_routers" or m.startswith("fake_routers.")]:
        del sys.modules[name]


def test_discovery_skips_empty_and_private_modules_and_sorts(fake_package):
    assert [n for n, _ in discover_routers(fake_package)] == ["alpha", "beta"]


def test_discovered_routers_serve_requests(fake_package):
    app = FastAPI()
    for _, router in discover_routers(fake_package):
        app.include_router(router)
    client = TestClient(app)
    assert client.get("/alpha/ping").json() == {"ok": "alpha"}
    assert client.get("/beta/ping").json() == {"ok": "beta"}


def test_non_router_attribute_fails_loudly(fake_package):
    (pathlib.Path(fake_package.__path__[0]) / "bad.py").write_text("router = object()")
    with pytest.raises(TypeError, match="APIRouter"):
        discover_routers(fake_package)