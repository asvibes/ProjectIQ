"""Requirement, risk and resource APIs: CRUD, codes, verification, ownership, derived data."""
from __future__ import annotations

from api_fixtures import add_document, db_session, make_company, make_project
from api_fixtures import client, company, other_project, project, storage_dir, uploads_dir  # noqa: F401
from app.models import Risk


# ------------------------------------------------------------------------ requirements
def test_requirement_lifecycle(client, project):
    base = f"/projects/{project['id']}/requirements"
    first = client.post(base, json={"description": "ISO 9001 certificate", "category": "certification", "is_mandatory": True})
    assert first.status_code == 201
    body = first.json()
    assert body["code"] == "REQ-001"
    assert body["origin"] == "manual"
    assert body["match_status"] == "Unknown"
    assert body["verification_status"] == "Requires review"
    assert body["quote_verified"] is None

    second = client.post(base, json={"description": "Five years' experience"}).json()
    assert second["code"] == "REQ-002"
    assert second["is_mandatory"] is None  # unknown stays unknown

    verified = client.post(f"{base}/{body['id']}/verify").json()
    assert verified["verification_status"] == "Verified" and verified["last_verified_at"]
    rejected = client.post(f"{base}/{second['id']}/reject").json()
    assert rejected["verification_status"] == "Rejected"

    patched = client.patch(
        f"{base}/{body['id']}", json={"match_status": "Met", "evidence_summary": "Certificate #12 on file"}
    ).json()
    assert patched["match_status"] == "Met"

    assert client.get(base).json()["total"] == 2
    assert client.get(base, params={"match_status": "Met"}).json()["total"] == 1
    assert client.get(base, params={"is_mandatory": "true"}).json()["total"] == 1
    assert client.get(base, params={"verification_status": "Rejected"}).json()["total"] == 1
    assert client.get(base, params={"category": "certification"}).json()["total"] == 1

    assert client.delete(f"{base}/{second['id']}").status_code == 204
    assert client.get(f"{base}/{second['id']}").status_code == 404
    # a deleted code is not reused below the current maximum
    assert client.post(base, json={"description": "Another"}).json()["code"] == "REQ-002"


def test_requirement_validation(client, project):
    base = f"/projects/{project['id']}/requirements"
    assert client.post(base, json={"description": ""}).status_code == 422
    assert client.post(base, json={"description": "x", "category": "bogus"}).status_code == 422
    assert client.post(base, json={"description": "x", "page_number": 0}).status_code == 422
    assert client.post(base, json={"description": "x", "quote_verified": True}).status_code == 422
    assert client.post(base, json={"description": "x", "origin": "extracted"}).status_code == 422
    assert client.post(base, json={"description": "x", "code": "REQ-009"}).status_code == 201
    assert client.post(base, json={"description": "y", "code": "REQ-009"}).status_code == 409
    rid = client.post(base, json={"description": "z"}).json()["id"]
    assert client.patch(f"{base}/{rid}", json={"description": None}).status_code == 422
    assert client.patch(f"{base}/{rid}", json={"verification_status": None}).status_code == 422
    assert client.get("/projects/999/requirements").status_code == 404


def test_requirements_are_isolated_between_projects(client, project, other_project):
    created = client.post(f"/projects/{project['id']}/requirements", json={"description": "Secret"}).json()
    foreign = f"/projects/{other_project['id']}/requirements/{created['id']}"
    assert client.get(foreign).status_code == 404
    assert client.patch(foreign, json={"notes": "x"}).status_code == 404
    assert client.delete(foreign).status_code == 404
    assert client.post(f"{foreign}/verify").status_code == 404
    assert client.post(f"{foreign}/reject").status_code == 404
    assert client.get(f"/projects/{other_project['id']}/requirements").json()["total"] == 0


def test_requirement_source_document_must_belong_to_project(client, engine, project, other_project):
    foreign_doc = add_document(engine, project_id=other_project["id"], storage_path="f.txt")
    own_doc = add_document(engine, project_id=project["id"], storage_path="o.txt")
    base = f"/projects/{project['id']}/requirements"
    assert client.post(base, json={"description": "x", "source_document_id": foreign_doc}).status_code == 422
    created = client.post(base, json={"description": "x", "source_document_id": own_doc})
    assert created.status_code == 201
    rid = created.json()["id"]
    assert client.patch(f"{base}/{rid}", json={"source_document_id": foreign_doc}).status_code == 422


# ------------------------------------------------------------------------------ risks
def test_risk_lifecycle_and_derived_score(client, engine, project):
    base = f"/projects/{project['id']}/risks"
    created = client.post(base, json={"title": "Steel price spike", "category": "commercial", "probability": 4, "impact": 5})
    assert created.status_code == 201
    risk = created.json()
    assert risk["code"] == "RISK-001" and risk["origin"] == "manual"
    assert risk["score"] is None  # only the scoring service may write it

    # a score written by the (future) scoring service is cleared when the ratings change
    with db_session(engine) as session:
        row = session.get(Risk, risk["id"])
        row.score = 20
        session.commit()
    assert client.get(f"{base}/{risk['id']}").json()["score"] == 20
    assert client.patch(f"{base}/{risk['id']}", json={"mitigation": "Fixed-price supply"}).json()["score"] == 20
    assert client.patch(f"{base}/{risk['id']}", json={"impact": 3}).json()["score"] is None

    assert client.post(f"{base}/{risk['id']}/verify").json()["verification_status"] == "Verified"
    assert client.post(f"{base}/{risk['id']}/reject").json()["verification_status"] == "Rejected"
    assert client.get(base, params={"category": "commercial"}).json()["total"] == 1
    assert client.get(base, params={"status": "closed"}).json()["total"] == 0
    assert client.delete(f"{base}/{risk['id']}").status_code == 204


def test_risk_validation_and_isolation(client, project, other_project):
    base = f"/projects/{project['id']}/risks"
    assert client.post(base, json={"title": "x", "probability": 6}).status_code == 422
    assert client.post(base, json={"title": "x", "impact": 0}).status_code == 422
    assert client.post(base, json={"title": "x", "score": 10}).status_code == 422  # derived, not accepted
    assert client.post(base, json={"title": ""}).status_code == 422
    assert client.post(base, json={"title": "a", "code": "RISK-005"}).status_code == 201
    assert client.post(base, json={"title": "b", "code": "RISK-005"}).status_code == 409

    risk_id = client.get(base).json()["items"][0]["id"]
    foreign = f"/projects/{other_project['id']}/risks/{risk_id}"
    assert client.get(foreign).status_code == 404
    assert client.patch(foreign, json={"notes": "x"}).status_code == 404
    assert client.delete(foreign).status_code == 404


def test_risk_scoring_action_is_not_implemented(client, project):
    response = client.post(f"/projects/{project['id']}/risks/score")
    assert response.status_code == 501
    assert "risk-scoring" in response.json()["detail"]
    assert client.post("/projects/999/risks/score").status_code == 404


# -------------------------------------------------------------------------- resources
def test_resource_lifecycle(client, project):
    base = f"/projects/{project['id']}/resources"
    created = client.post(
        base,
        json={"resource_type": "personnel", "name": "Welders", "required_quantity": 8, "unit": "month", "unit_cost": "3200"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["available_quantity"] is None  # unknown stays unknown
    assert body["unit_cost"] == "3200.00"

    patched = client.patch(f"{base}/{body['id']}", json={"available_quantity": 5}).json()
    assert patched["available_quantity"] == 5
    assert client.get(base, params={"resource_type": "personnel"}).json()["total"] == 1
    assert client.get(base, params={"resource_type": "equipment"}).json()["total"] == 0
    assert client.delete(f"{base}/{body['id']}").status_code == 204


def test_resource_validation(client, project):
    base = f"/projects/{project['id']}/resources"
    assert client.post(base, json={"name": ""}).status_code == 422
    assert client.post(base, json={"name": "x", "required_quantity": -1}).status_code == 422
    assert client.post(base, json={"name": "x", "unit_cost": "-3"}).status_code == 422
    assert client.post(
        base, json={"name": "x", "required_from": "2026-02-01", "required_to": "2026-01-01"}
    ).status_code == 422
    rid = client.post(base, json={"name": "x"}).json()["id"]
    assert client.patch(f"{base}/{rid}", json={"required_from": "2026-02-01", "required_to": "2026-01-01"}).status_code == 422


def test_resource_company_links_stay_inside_the_projects_company(client, project):
    own_role = client.post(
        f"/companies/{project['company_id']}/workforce-roles", json={"role": "Welder", "headcount": 3}
    ).json()
    own_equipment = client.post(f"/companies/{project['company_id']}/equipment", json={"name": "Crane"}).json()
    other_company = make_company(client, name="Rival Ltd")
    foreign_role = client.post(
        f"/companies/{other_company['id']}/workforce-roles", json={"role": "Welder", "headcount": 9}
    ).json()

    base = f"/projects/{project['id']}/resources"
    ok = client.post(base, json={"name": "Welders", "resource_type": "personnel", "company_workforce_role_id": own_role["id"]})
    assert ok.status_code == 201
    assert client.post(
        base, json={"name": "Welders", "resource_type": "personnel", "company_workforce_role_id": foreign_role["id"]}
    ).status_code == 422
    assert client.post(
        base, json={"name": "W", "resource_type": "equipment", "company_workforce_role_id": own_role["id"]}
    ).status_code == 422  # link kind must match the type
    assert client.post(
        base,
        json={
            "name": "Both",
            "resource_type": "personnel",
            "company_workforce_role_id": own_role["id"],
            "company_equipment_id": own_equipment["id"],
        },
    ).status_code == 422
    assert client.post(
        base, json={"name": "Crane", "resource_type": "equipment", "company_equipment_id": own_equipment["id"]}
    ).status_code == 201
    assert client.post(
        base, json={"name": "Crane", "resource_type": "equipment", "company_equipment_id": 9999}
    ).status_code == 422


def test_resources_are_isolated_between_projects(client, project, other_project):
    created = client.post(f"/projects/{project['id']}/resources", json={"name": "Crane"}).json()
    foreign = f"/projects/{other_project['id']}/resources/{created['id']}"
    assert client.get(foreign).status_code == 404
    assert client.patch(foreign, json={"notes": "x"}).status_code == 404
    assert client.delete(foreign).status_code == 404


def test_resource_gap_analysis_is_not_implemented(client, project):
    response = client.get(f"/projects/{project['id']}/resources/gaps")
    assert response.status_code == 501
    assert client.get("/projects/999/resources/gaps").status_code == 404
