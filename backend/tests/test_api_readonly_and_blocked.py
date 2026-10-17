"""Briefing, reports, fit, chat and settings APIs: stored-data reads and honest 501s."""
from __future__ import annotations

import pytest

from api_fixtures import add_document, db_session, make_company, make_project
from api_fixtures import client, company, other_project, project, storage_dir, uploads_dir  # noqa: F401
from app.models import Artifact, ArtifactFormat, ArtifactType, Requirement


def add_artifact(engine, project_id, **fields):
    defaults = dict(artifact_type=ArtifactType.OTHER, file_format=ArtifactFormat.OTHER, title="Output")
    with db_session(engine) as session:
        artifact = Artifact(project_id=project_id, **{**defaults, **fields})
        session.add(artifact)
        session.commit()
        return artifact.id


# -------------------------------------------------------------------------- briefing
def test_briefing_reads_latest_and_versions(client, engine, project, other_project):
    base = f"/projects/{project['id']}/briefing"
    assert client.get(base).status_code == 404  # nothing generated yet
    assert client.get(f"{base}/versions").json()["total"] == 0

    add_artifact(engine, project["id"], artifact_type=ArtifactType.BRIEFING, file_format=ArtifactFormat.MARKDOWN,
                 title="Briefing v1", content="# v1", version=1)
    add_artifact(engine, project["id"], artifact_type=ArtifactType.BRIEFING, file_format=ArtifactFormat.MARKDOWN,
                 title="Briefing v2", content="# v2", version=2)
    add_artifact(engine, project["id"], artifact_type=ArtifactType.RISK_REGISTER, title="Not a briefing", content="x")
    add_artifact(engine, other_project["id"], artifact_type=ArtifactType.BRIEFING, title="Other project", content="no")

    latest = client.get(base).json()
    assert latest["title"] == "Briefing v2" and latest["content"] == "# v2" and latest["has_content"] is True
    assert "storage_path" not in latest
    versions = client.get(f"{base}/versions").json()
    assert [v["version"] for v in versions["items"]] == [2, 1]
    assert all("content" not in v for v in versions["items"])

    assert client.get("/projects/999/briefing").status_code == 404


def test_briefing_generation_is_not_implemented(client, project):
    response = client.post(f"/projects/{project['id']}/briefing/generate")
    assert response.status_code == 501
    assert "drafter" in response.json()["detail"]
    assert client.post("/projects/999/briefing/generate").status_code == 404


# --------------------------------------------------------------------------- reports
def test_reports_list_detail_and_downloads(client, engine, project, other_project, storage_dir):
    base = f"/projects/{project['id']}/reports"
    (storage_dir / "generated").mkdir()
    (storage_dir / "generated" / "r1.csv").write_bytes(b"a,b\n1,2\n")
    file_id = add_artifact(
        engine, project["id"], artifact_type=ArtifactType.REQUIREMENTS_REGISTER, file_format=ArtifactFormat.CSV,
        title="Requirements register", storage_path="generated/r1.csv", mime_type="text/csv",
    )
    inline_id = add_artifact(
        engine, project["id"], artifact_type=ArtifactType.BRIEFING, file_format=ArtifactFormat.MARKDOWN,
        title="Draft briefing", content="# Hello",
    )
    foreign_id = add_artifact(engine, other_project["id"], title="Foreign", content="secret")

    listing = client.get(base).json()
    assert listing["total"] == 2
    assert all("storage_path" not in item for item in listing["items"])
    assert client.get(base, params={"artifact_type": "briefing"}).json()["total"] == 1

    detail = client.get(f"{base}/{file_id}").json()
    assert detail["has_file"] is True and detail["has_content"] is False

    download = client.get(f"{base}/{file_id}/download")
    assert download.status_code == 200
    assert download.content == b"a,b\n1,2\n"
    assert download.headers["content-type"].startswith("text/csv")
    assert "Requirements_register.csv" in download.headers["content-disposition"]

    inline = client.get(f"{base}/{inline_id}/download")
    assert inline.status_code == 200 and inline.text == "# Hello"
    assert inline.headers["content-type"].startswith("text/markdown")
    assert "Draft_briefing.md" in inline.headers["content-disposition"]

    assert client.get(f"{base}/{foreign_id}").status_code == 404
    assert client.get(f"{base}/{foreign_id}/download").status_code == 404


def test_report_download_never_leaves_the_storage_folder(client, engine, project, storage_dir, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("top secret")
    try:
        (storage_dir / "link.txt").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"Cannot create symlink on this system: {exc}")
    base = f"/projects/{project['id']}/reports"
    linked = add_artifact(engine, project["id"], title="Linked", storage_path="link.txt")
    missing = add_artifact(engine, project["id"], title="Missing", storage_path="gone.txt")
    for artifact_id in (linked, missing):
        response = client.get(f"{base}/{artifact_id}/download")
        assert response.status_code == 404
        assert "top secret" not in response.text


def test_report_generation_is_not_implemented(client, project):
    base = f"/projects/{project['id']}/reports/generate"
    response = client.post(base, json={"artifact_type": "briefing", "file_format": "docx"})
    assert response.status_code == 501
    assert "export" in response.json()["detail"]
    assert client.post(base, json={"artifact_type": "bogus", "file_format": "docx"}).status_code == 422
    assert client.post("/projects/999/reports/generate", json={"artifact_type": "briefing", "file_format": "docx"}).status_code == 404


# ------------------------------------------------------------------------------- fit
def test_fit_summary_counts_stored_states(client, engine, project, other_project):
    base = f"/projects/{project['id']}/requirements"
    ids = [
        client.post(base, json={"description": "a", "is_mandatory": True}).json()["id"],
        client.post(base, json={"description": "b", "is_mandatory": True}).json()["id"],
        client.post(base, json={"description": "c", "is_mandatory": False}).json()["id"],
        client.post(base, json={"description": "d"}).json()["id"],
    ]
    client.patch(f"{base}/{ids[0]}", json={"match_status": "Met"})
    client.patch(f"{base}/{ids[1]}", json={"match_status": "Not met"})
    client.post(f"{base}/{ids[0]}/verify")
    client.post(f"/projects/{other_project['id']}/requirements", json={"description": "elsewhere", "is_mandatory": True})

    summary = client.get(f"/projects/{project['id']}/fit/summary").json()
    assert summary["company_id"] == project["company_id"]
    assert summary["total_requirements"] == 4
    assert summary["by_match_status"]["Met"] == 1
    assert summary["by_match_status"]["Not met"] == 1
    assert summary["by_match_status"]["Unknown"] == 2
    assert summary["mandatory_by_match_status"]["Met"] == 1
    assert summary["mandatory_by_match_status"]["Not met"] == 1
    assert summary["mandatory_by_match_status"]["Unknown"] == 0
    assert summary["mandatory_unspecified"] == 1
    assert summary["unreviewed_requirements"] == 3
    assert summary["automated_matching_available"] is False
    assert "No automated matching" in summary["basis"]
    assert "score" not in summary and "recommendation" not in summary


def test_fit_summary_for_empty_and_unknown_projects(client, project):
    summary = client.get(f"/projects/{project['id']}/fit/summary").json()
    assert summary["total_requirements"] == 0
    assert set(summary["by_match_status"].values()) == {0}
    assert client.get("/projects/999/fit/summary").status_code == 404


def test_fit_matching_is_not_implemented(client, project):
    response = client.post(f"/projects/{project['id']}/fit/run")
    assert response.status_code == 501
    assert "matcher" in response.json()["detail"]
    assert client.post("/projects/999/fit/run").status_code == 404


# ------------------------------------------------------------------------------ chat
def test_chat_validates_then_reports_not_implemented(client, project):
    url = f"/projects/{project['id']}/chat"
    assert client.post(url, json={"message": ""}).status_code == 422
    assert client.post(url, json={"message": "x" * 4001}).status_code == 422
    assert client.post(url, json={"message": "hi", "model": "gemma"}).status_code == 422
    assert client.post("/projects/999/chat", json={"message": "hi"}).status_code == 404
    response = client.post(url, json={"message": "What are the deadlines?"})
    assert response.status_code == 501
    assert "Ollama" in response.json()["detail"]
    assert "deadlines" not in response.text  # the question is not echoed back


# ---------------------------------------------------------------------------- settings
def test_settings_expose_only_safe_values(client):
    response = client.get("/settings")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"version", "environment", "default_currency", "database_backend"}
    assert body["environment"] == "test"
    assert body["database_backend"] == "sqlite"
    text = response.text.lower()
    for forbidden in ("sqlite://", "storage", "password", "secret", "token", "key"):
        assert forbidden not in text
    assert client.put("/settings", json={"default_currency": "EUR"}).status_code == 405
    assert client.patch("/settings", json={"default_currency": "EUR"}).status_code == 405
