"""Shared fixtures and helpers for the API tests (imported into the test modules)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import get_db
from app.main import create_app
from app.models import Company, Project
from app.routers._common import get_storage_dir
from app.routers.documents import get_upload_dir


@pytest.fixture()
def uploads_dir(tmp_path):
    path = tmp_path / "uploads"
    path.mkdir()
    return path


@pytest.fixture()
def storage_dir(tmp_path):
    path = tmp_path / "storage"
    path.mkdir()
    return path


@pytest.fixture()
def client(engine, uploads_dir, storage_dir):
    app = create_app(init_database=False)

    def _db():
        with Session(engine, autoflush=False, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_upload_dir] = lambda: uploads_dir
    app.dependency_overrides[get_storage_dir] = lambda: storage_dir
    return TestClient(app)


@pytest.fixture()
def company(client):
    return make_company(client)


@pytest.fixture()
def project(client, company):
    return make_project(client, company["id"])


@pytest.fixture()
def other_project(client, company):
    return make_project(client, company["id"], name="Other project")


def make_company(client, **overrides):
    body = {"name": "Acme Steel", **overrides}
    response = client.post("/companies", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def make_project(client, company_id, **overrides):
    body = {"company_id": company_id, "name": "Steel plant", **overrides}
    response = client.post("/projects", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def db_session(engine):
    return Session(engine, autoflush=False, expire_on_commit=False)


def add_document(engine, *, project_id=None, company_id=None, storage_path="abc.txt"):
    from app.models import Document, DocumentType

    with db_session(engine) as session:
        document = Document(
            project_id=project_id,
            company_id=company_id,
            document_type=DocumentType.OTHER,
            original_filename="x.txt",
            storage_path=storage_path,
        )
        session.add(document)
        session.commit()
        return document.id
