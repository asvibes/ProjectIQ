"""POST /projects/{id}/financial-models/{id}/calculate: stores deterministic engine results."""
from __future__ import annotations

from api_fixtures import client, company, other_project, project, storage_dir, uploads_dir  # noqa: F401


def make_model(client, project_id, **overrides):
    body = {
        "name": "Base case",
        "currency": "USD",
        "bid_price": "3000",
        "duration_months": 3,
        "payment_terms_days": 30,
        "advance_payment_rate": "0.10",
        "retention_rate": "0.05",
        "contingency_rate": "0.10",
        "overhead_rate": "0.10",
        "target_margin_rate": "0.20",
        **overrides,
    }
    response = client.post(f"/projects/{project_id}/financial-models", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def add_item(client, project_id, model_id, **fields):
    body = {"category": "materials", "description": "Steel", "quantity": "10", "unit_cost": "100",
            "cost_behavior": "variable", "start_month": 0, "end_month": 2, "verification_status": "Verified", **fields}
    response = client.post(f"/projects/{project_id}/financial-models/{model_id}/cost-items", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def populated_model(client, project_id):
    model = make_model(client, project_id)
    add_item(client, project_id, model["id"])
    add_item(client, project_id, model["id"], category="labour", description="Crew", quantity="5",
             unit_cost="200", cost_behavior="fixed")
    return model


def url(project_id, model_id):
    return f"/projects/{project_id}/financial-models/{model_id}/calculate"


def test_calculate_stores_results_timestamp_and_version(client, project):
    model = populated_model(client, project["id"])
    assert model["results"] is None and model["calculated_at"] is None

    response = client.post(url(project["id"], model["id"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["engine_version"] == "finance-1.0.0"
    assert body["calculated_at"] is not None
    results = body["results"]
    assert results["total_cost"] == "2420.00"  # 2,000 + 10% contingency + 10% overhead on 2,200
    assert results["profit"] == "580.00" and results["margin_rate"] == "0.1933"
    assert results["suggested_price"] == "3025.00"
    assert results["costs_complete"] is True
    assert results["provenance"]["inputs_fingerprint"]

    # persisted: a fresh GET returns the same results
    stored = client.get(f"/projects/{project['id']}/financial-models/{model['id']}").json()
    assert stored["results"] == results and stored["calculated_at"] == body["calculated_at"]


def test_recalculating_unchanged_inputs_gives_identical_results(client, project):
    model = populated_model(client, project["id"])
    first = client.post(url(project["id"], model["id"])).json()["results"]
    second = client.post(url(project["id"], model["id"])).json()["results"]
    assert first == second


def test_editing_inputs_then_recalculating_updates_results_and_fingerprint(client, project):
    model = populated_model(client, project["id"])
    first = client.post(url(project["id"], model["id"])).json()["results"]
    client.patch(f"/projects/{project['id']}/financial-models/{model['id']}", json={"bid_price": "3500"})
    # Editing inputs does not silently rewrite stored results...
    stale = client.get(f"/projects/{project['id']}/financial-models/{model['id']}").json()["results"]
    assert stale == first
    # ...recalculating does, and the fingerprint shows the inputs changed.
    second = client.post(url(project["id"], model["id"])).json()["results"]
    assert second["profit"] == "1080.00"
    assert second["provenance"]["inputs_fingerprint"] != first["provenance"]["inputs_fingerprint"]


def test_unknown_inputs_are_reported_not_treated_as_zero(client, project):
    model = make_model(client, project["id"], bid_price=None, contingency_rate=None)
    add_item(client, project["id"], model["id"], unit_cost=None)  # unknown unit cost
    response = client.post(url(project["id"], model["id"]))
    assert response.status_code == 200
    results = response.json()["results"]
    assert results["costs_complete"] is False
    assert results["total_cost"] is None and results["profit"] is None
    assert results["pricing_outcome"] == "incomplete_costs"
    assert any("unit cost" in reason for reason in results["cost_model"]["incomplete_reasons"])


def test_model_without_cost_lines_is_incomplete_not_free(client, project):
    model = make_model(client, project["id"])
    results = client.post(url(project["id"], model["id"])).json()["results"]
    assert results["costs_complete"] is False and results["total_cost"] is None
    assert "no cost lines" in results["cost_model"]["incomplete_reasons"]


def test_rejected_lines_are_excluded(client, project):
    model = populated_model(client, project["id"])
    add_item(client, project["id"], model["id"], description="Rejected quote", unit_cost="99999",
             verification_status="Rejected")
    results = client.post(url(project["id"], model["id"])).json()["results"]
    assert results["total_cost"] == "2420.00"
    assert results["cost_model"]["rejected_line_count"] == 1


def test_unknown_foreign_and_missing_resources_answer_404(client, project, other_project):
    model = populated_model(client, project["id"])
    assert client.post(url(project["id"], 999)).status_code == 404
    assert client.post(url(other_project["id"], model["id"])).status_code == 404  # another project's model
    assert client.post(url(999, model["id"])).status_code == 404


def test_clients_cannot_write_results_directly(client, project):
    model = populated_model(client, project["id"])
    response = client.patch(
        f"/projects/{project['id']}/financial-models/{model['id']}", json={"results": {"total_cost": "1.00"}}
    )
    assert response.status_code == 422
    assert client.get(f"/projects/{project['id']}/financial-models/{model['id']}").json()["results"] is None
