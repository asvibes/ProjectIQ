"""Project and company APIs: CRUD, validation, verification rules, isolation, file cleanup."""
from __future__ import annotations

from sqlalchemy import select

from api_fixtures import add_document, db_session, make_company, make_project
from api_fixtures import client, company, other_project, project, storage_dir, uploads_dir  # noqa: F401
from app.models import Document


# ------------------------------------------------------------------------------ projects
def test_project_round_trip(client, company):
    created = client.post(
        "/projects",
        json={
            "company_id": company["id"],
            "name": "Steel plant",
            "currency": "eur",
            "budget": "1250000.50",
            "deadline": "2027-01-31T00:00:00Z",
            "deliverables": ["Design", "Build"],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["currency"] == "EUR"
    assert body["status"] == "draft"
    assert body["budget"] == "1250000.50"
    assert body["deliverables"] == ["Design", "Build"]

    pid = body["id"]
    assert client.get(f"/projects/{pid}").json()["name"] == "Steel plant"

    patched = client.patch(f"/projects/{pid}", json={"status": "pursuing", "client": "Ministry"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "pursuing"
    assert patched.json()["client"] == "Ministry"

    listing = client.get("/projects", params={"company_id": company["id"], "status": "pursuing"}).json()
    assert listing["total"] == 1 and listing["items"][0]["id"] == pid
    assert client.get("/projects", params={"status": "declined"}).json()["total"] == 0

    assert client.delete(f"/projects/{pid}").status_code == 204
    assert client.get(f"/projects/{pid}").status_code == 404


def test_project_requires_existing_company(client):
    response = client.post("/projects", json={"company_id": 999, "name": "Orphan"})
    assert response.status_code == 404


def test_project_validation(client, company):
    base = {"company_id": company["id"], "name": "P"}
    assert client.post("/projects", json={**base, "name": ""}).status_code == 422
    assert client.post("/projects", json={**base, "budget": "-5"}).status_code == 422
    assert client.post("/projects", json={**base, "currency": "EURO"}).status_code == 422
    assert client.post("/projects", json={**base, "deadline": "2027-01-31T00:00:00"}).status_code == 422  # naive
    assert client.post("/projects", json={**base, "status": "bogus"}).status_code == 422
    assert client.post("/projects", json={**base, "surprise": 1}).status_code == 422  # unknown field


def test_project_patch_cannot_null_required_fields_or_move_company(client, project):
    pid = project["id"]
    assert client.patch(f"/projects/{pid}", json={"name": None}).status_code == 422
    assert client.patch(f"/projects/{pid}", json={"company_id": 2}).status_code == 422
    assert client.patch("/projects/9999", json={"name": "x"}).status_code == 404


def test_deleting_project_removes_children_and_stored_files(client, engine, project, uploads_dir, storage_dir):
    (uploads_dir / "tender.txt").write_text("data")
    add_document(engine, project_id=project["id"], storage_path="tender.txt")
    client.post(f"/projects/{project['id']}/requirements", json={"description": "Must have ISO 9001"})

    assert client.delete(f"/projects/{project['id']}").status_code == 204

    assert not (uploads_dir / "tender.txt").exists()
    with db_session(engine) as session:
        assert session.scalars(select(Document)).all() == []
    assert client.get(f"/projects/{project['id']}/requirements").status_code == 404


# ----------------------------------------------------------------------------- companies
def test_company_round_trip(client):
    created = client.post(
        "/companies", json={"name": "Acme", "annual_revenue": "5000000", "locations": ["Pune"], "currency": "inr"}
    )
    assert created.status_code == 201
    body = created.json()
    assert body["currency"] == "INR" and body["annual_revenue"] == "5000000.00"
    cid = body["id"]

    assert client.patch(f"/companies/{cid}", json={"industry": "Steel"}).json()["industry"] == "Steel"
    assert client.get("/companies").json()["total"] == 1
    assert client.patch(f"/companies/{cid}", json={"name": None}).status_code == 422
    assert client.post("/companies", json={"name": "X", "annual_revenue": "-1"}).status_code == 422
    assert client.get("/companies/999").status_code == 404
    assert client.delete(f"/companies/{cid}").status_code == 204
    assert client.get(f"/companies/{cid}").status_code == 404


def test_deleting_company_removes_projects_and_files(client, engine, company, uploads_dir):
    project = make_project(client, company["id"])
    (uploads_dir / "a.txt").write_text("1")
    (uploads_dir / "b.txt").write_text("2")
    add_document(engine, company_id=company["id"], storage_path="a.txt")
    add_document(engine, project_id=project["id"], storage_path="b.txt")

    assert client.delete(f"/companies/{company['id']}").status_code == 204
    assert list(uploads_dir.iterdir()) == []
    assert client.get(f"/projects/{project['id']}").status_code == 404


def test_company_field_verification(client, engine, company):
    cid = company["id"]
    ok = client.put(f"/companies/{cid}/field-verification/annual_revenue", json={"status": "Verified"})
    assert ok.status_code == 200
    entry = ok.json()["field_verification"]["annual_revenue"]
    assert entry["status"] == "Verified" and entry["last_verified_at"]

    assert client.put(f"/companies/{cid}/field-verification/nonsense", json={"status": "Verified"}).status_code == 422
    assert client.put(f"/companies/{cid}/field-verification/name", json={"status": "bogus"}).status_code == 422

    other = make_company(client, name="Other co")
    foreign_doc = add_document(engine, company_id=other["id"])
    response = client.put(
        f"/companies/{cid}/field-verification/name",
        json={"status": "Verified", "source_document_id": foreign_doc},
    )
    assert response.status_code == 422


def test_editing_a_verified_field_resets_its_verification(client, company):
    cid = company["id"]
    client.patch(f"/companies/{cid}", json={"annual_revenue": "100"})
    client.put(f"/companies/{cid}/field-verification/annual_revenue", json={"status": "Verified"})

    # unrelated edit leaves it verified
    client.patch(f"/companies/{cid}", json={"industry": "Steel"})
    assert client.get(f"/companies/{cid}").json()["field_verification"]["annual_revenue"]["status"] == "Verified"

    # changing the value invalidates the earlier verification
    client.patch(f"/companies/{cid}", json={"annual_revenue": "200"})
    assert client.get(f"/companies/{cid}").json()["field_verification"]["annual_revenue"]["status"] == "Requires review"


# ------------------------------------------------------------------ company child records
def test_workforce_role_crud_and_rules(client, company):
    cid = company["id"]
    url = f"/companies/{cid}/workforce-roles"
    created = client.post(url, json={"role": "Welder", "department": "Site", "headcount": 10, "available_headcount": 4})
    assert created.status_code == 201
    body = created.json()
    assert body["verification_status"] == "Requires review" and body["last_verified_at"] is None
    rid = body["id"]

    assert client.post(url, json={"role": "Welder", "department": "Site"}).status_code == 409  # duplicate
    assert client.post(url, json={"role": "Fitter", "headcount": 2, "available_headcount": 5}).status_code == 422
    assert client.patch(f"{url}/{rid}", json={"available_headcount": 11}).status_code == 422
    assert client.patch(f"{url}/{rid}", json={"verification_status": None}).status_code == 422

    verified = client.patch(f"{url}/{rid}", json={"verification_status": "Verified"})
    assert verified.json()["verification_status"] == "Verified"
    assert verified.json()["last_verified_at"] is not None

    assert client.get(url).json()["total"] == 1
    assert client.get(url, params={"verification_status": "Verified"}).json()["total"] == 1
    assert client.get(url, params={"verification_status": "Rejected"}).json()["total"] == 0
    assert client.delete(f"{url}/{rid}").status_code == 204
    assert client.get(f"{url}/{rid}").status_code == 404


def test_equipment_certification_and_past_project(client, company):
    cid = company["id"]
    eq = client.post(f"/companies/{cid}/equipment", json={"name": "Crane", "quantity": 2, "ownership": "owned"})
    assert eq.status_code == 201 and eq.json()["ownership"] == "owned"
    assert client.post(f"/companies/{cid}/equipment", json={"name": "Bad", "quantity": -1}).status_code == 422

    cert = client.post(
        f"/companies/{cid}/certifications",
        json={"name": "ISO 9001", "issued_date": "2024-01-01", "expiry_date": "2027-01-01"},
    )
    assert cert.status_code == 201
    bad = client.post(
        f"/companies/{cid}/certifications",
        json={"name": "ISO 14001", "issued_date": "2024-01-01", "expiry_date": "2023-01-01"},
    )
    assert bad.status_code == 422
    assert client.patch(
        f"/companies/{cid}/certifications/{cert.json()['id']}", json={"expiry_date": "2020-01-01"}
    ).status_code == 422

    past = client.post(
        f"/companies/{cid}/past-projects",
        json={"title": "Bridge", "contract_value": "900000", "start_date": "2020-01-01", "completion_date": "2021-06-01"},
    )
    assert past.status_code == 201 and past.json()["contract_value"] == "900000.00"
    assert client.post(
        f"/companies/{cid}/past-projects",
        json={"title": "X", "start_date": "2021-01-01", "completion_date": "2020-01-01"},
    ).status_code == 422


def test_child_records_are_isolated_between_companies(client, company):
    other = make_company(client, name="Other co")
    created = client.post(f"/companies/{company['id']}/equipment", json={"name": "Crane"}).json()
    foreign = f"/companies/{other['id']}/equipment/{created['id']}"
    assert client.get(foreign).status_code == 404
    assert client.patch(foreign, json={"name": "Stolen"}).status_code == 404
    assert client.delete(foreign).status_code == 404
    assert client.get(f"/companies/{company['id']}/equipment/{created['id']}").json()["name"] == "Crane"
    assert client.get("/companies/999/equipment").status_code == 404


def test_child_source_document_must_belong_to_the_company(client, engine, company):
    other = make_company(client, name="Other co")
    foreign_doc = add_document(engine, company_id=other["id"])
    own_doc = add_document(engine, company_id=company["id"], storage_path="own.txt")
    url = f"/companies/{company['id']}/equipment"
    assert client.post(url, json={"name": "Crane", "source_document_id": foreign_doc}).status_code == 422
    assert client.post(url, json={"name": "Crane", "source_document_id": own_doc}).status_code == 201
