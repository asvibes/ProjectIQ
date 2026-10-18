"""Scenario API: baseline rules, calculation from a base model, and stored comparison."""
from __future__ import annotations

from api_fixtures import client, company, other_project, project, storage_dir, uploads_dir  # noqa: F401
from test_api_financial_calculate import populated_model


def make_scenario(client, project_id, **fields):
    body = {"name": "Scenario", "kind": "price", **fields}
    response = client.post(f"/projects/{project_id}/scenarios", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def calc(client, project_id, scenario_id):
    return client.post(f"/projects/{project_id}/scenarios/{scenario_id}/calculate")


def test_scenario_is_calculated_from_model_and_overrides(client, project):
    model = populated_model(client, project["id"])
    scenario = make_scenario(
        client, project["id"], name="Higher price", financial_model_id=model["id"],
        overrides={"bid_price": "3500"}, assumptions=["Client accepts a 17% uplift"],
    )
    assert scenario["results"] is None

    response = calc(client, project["id"], scenario["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["engine_version"] == "finance-1.0.0" and body["calculated_at"] is not None
    results = body["results"]
    assert results["total_cost"] == "2420.00" and results["profit"] == "1080.00"
    assert results["deltas_vs_base"]["profit"] == "500.00"
    assert results["overrides_applied"] == {"bid_price": "3500"}
    # the scenario never changes the base model's stored data
    base = client.get(f"/projects/{project['id']}/financial-models/{model['id']}").json()
    assert base["bid_price"] == "3000.00" and base["results"] is None


def test_scenario_without_a_base_model_cannot_be_calculated(client, project):
    scenario = make_scenario(client, project["id"], overrides={"bid_price": "1"})
    response = calc(client, project["id"], scenario["id"])
    assert response.status_code == 422
    assert "financial model" in response.json()["detail"]
    assert client.get(f"/projects/{project['id']}/scenarios/{scenario['id']}").json()["results"] is None


def test_invalid_overrides_give_422_and_store_nothing(client, project):
    model = populated_model(client, project["id"])
    for overrides in ({"nonsense": 1}, {"cost_multipliers": {"materials": -2}}, {"contingency_rate": 4}):
        scenario = make_scenario(client, project["id"], name=f"bad {list(overrides)[0]}",
                                 financial_model_id=model["id"], overrides=overrides)
        response = calc(client, project["id"], scenario["id"])
        assert response.status_code == 422, overrides
        assert "cannot be calculated" in response.json()["detail"]
        stored = client.get(f"/projects/{project['id']}/scenarios/{scenario['id']}").json()
        assert stored["results"] is None and stored["calculated_at"] is None


def test_baseline_equals_the_unchanged_base_model(client, project):
    model = populated_model(client, project["id"])
    baseline = make_scenario(client, project["id"], name="Baseline", kind="baseline",
                             financial_model_id=model["id"])
    scenario_results = calc(client, project["id"], baseline["id"]).json()["results"]
    model_results = client.post(
        f"/projects/{project['id']}/financial-models/{model['id']}/calculate"
    ).json()["results"]
    for key in ("total_cost", "profit", "margin_rate", "suggested_price", "peak_funding_requirement",
                "break_even_status", "cash_flow_status"):
        assert scenario_results[key] == model_results[key], key
    assert all(v in ("0.00", "0.0000") for v in scenario_results["deltas_vs_base"].values())


def test_baseline_with_overrides_is_refused(client, project):
    model = populated_model(client, project["id"])
    baseline = make_scenario(client, project["id"], name="Baseline", kind="baseline",
                             financial_model_id=model["id"], overrides={"bid_price": "1"})
    response = calc(client, project["id"], baseline["id"])
    assert response.status_code == 422 and "baseline" in response.json()["detail"]


def test_only_one_baseline_per_project_and_unique_names(client, project, other_project):
    make_scenario(client, project["id"], name="Baseline", kind="baseline")
    second = client.post(f"/projects/{project['id']}/scenarios", json={"name": "Another", "kind": "baseline"})
    assert second.status_code == 409
    duplicate = client.post(f"/projects/{project['id']}/scenarios", json={"name": "Baseline", "kind": "price"})
    assert duplicate.status_code == 409
    # a different project may have its own baseline
    assert client.post(f"/projects/{other_project['id']}/scenarios",
                       json={"name": "Baseline", "kind": "baseline"}).status_code == 201


def test_compare_shows_calculated_scenarios_side_by_side(client, project):
    model = populated_model(client, project["id"])
    baseline = make_scenario(client, project["id"], name="Baseline", kind="baseline", financial_model_id=model["id"])
    high = make_scenario(client, project["id"], name="High price", financial_model_id=model["id"],
                         overrides={"bid_price": "3500"})
    costly = make_scenario(client, project["id"], name="Steel +50%", kind="assumptions",
                           financial_model_id=model["id"], overrides={"cost_multipliers": {"materials": "1.5"}})
    pending = make_scenario(client, project["id"], name="Not run yet", financial_model_id=model["id"])
    for scenario in (baseline, high, costly):
        assert calc(client, project["id"], scenario["id"]).status_code == 200

    ids = [baseline["id"], high["id"], costly["id"], pending["id"]]
    response = client.get(f"/projects/{project['id']}/scenarios/compare", params={"ids": ids})
    assert response.status_code == 200, response.text
    body = response.json()
    profit = {int(k): v for k, v in body["metrics"]["profit"].items()}
    assert profit[baseline["id"]] == "580.00"
    assert profit[high["id"]] == "1080.00"
    assert profit[costly["id"]] == "-25.00"
    assert profit[pending["id"]] is None
    assert body["not_calculated"] == [pending["id"]]


def test_scenario_of_another_project_or_deleted_model(client, project, other_project):
    model = populated_model(client, project["id"])
    scenario = make_scenario(client, project["id"], financial_model_id=model["id"], overrides={"bid_price": "3200"})
    # foreign project cannot reach it
    assert calc(client, other_project["id"], scenario["id"]).status_code == 404
    assert calc(client, project["id"], 999).status_code == 404
    # a scenario cannot be linked to another project's model
    foreign_model = populated_model(client, other_project["id"])
    response = client.post(f"/projects/{project['id']}/scenarios",
                           json={"name": "Cross", "financial_model_id": foreign_model["id"]})
    assert response.status_code == 422

    # deleting the model detaches the scenario but keeps stored results; recalculating needs a model
    assert calc(client, project["id"], scenario["id"]).status_code == 200
    client.delete(f"/projects/{project['id']}/financial-models/{model['id']}")
    kept = client.get(f"/projects/{project['id']}/scenarios/{scenario['id']}").json()
    assert kept["financial_model_id"] is None and kept["results"]["profit"] == "780.00"  # 3,200 - 2,420
    assert calc(client, project["id"], scenario["id"]).status_code == 422
