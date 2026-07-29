from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app import db
from app.main import app


HEADERS = {
    "X-KArchitect-Token": "test-secret",
    "X-KArchitect-User": "alice",
}


def test_project_lifecycle(tmp_path: Path, monkeypatch) -> None:
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(config, "DB_PATH", test_db)
    monkeypatch.setattr(db, "DB_PATH", test_db)
    monkeypatch.setattr("app.main.INTERNAL_TOKEN", "test-secret")
    with TestClient(app) as client:
        created = client.post(
            "/api/projects",
            json={"name": "テスト設計", "initial_idea": "予約システム"},
            headers=HEADERS,
        )
        assert created.status_code == 200
        project = created.json()
        assert project["name"] == "テスト設計"
        assert project["requirements"]["summary"] == "予約システム"

        fetched = client.get(f"/api/projects/{project['id']}", headers=HEADERS)
        assert fetched.status_code == 200

        markdown = client.get(f"/api/projects/{project['id']}/document.md", headers=HEADERS)
        assert markdown.status_code == 200
        assert "テスト設計 システム設計書" in markdown.text

        mermaid = client.get(
            f"/api/projects/{project['id']}/mermaid/architecture",
            headers=HEADERS,
        )
        assert mermaid.status_code == 200
        assert "flowchart LR" in mermaid.text

        assert client.get("/api/projects").status_code == 401
        assert client.get(
            f"/api/projects/{project['id']}",
            headers={**HEADERS, "X-KArchitect-User": "bob"},
        ).status_code == 404
        assert client.get(
            "/api/projects",
            headers={**HEADERS, "X-KArchitect-User": "bob"},
        ).json() == []
