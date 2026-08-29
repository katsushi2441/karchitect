from pathlib import Path

from fastapi.testclient import TestClient

from app import config, db
from app.main import app


HEADERS = {
    "X-KArchitect-Token": "test-secret",
    "X-KArchitect-User": "guard-test",
}


def _client(tmp_path: Path, monkeypatch):
    test_db = tmp_path / "guard.db"
    monkeypatch.setattr(config, "DB_PATH", test_db)
    monkeypatch.setattr(db, "DB_PATH", test_db)
    monkeypatch.setattr("app.main.INTERNAL_TOKEN", "test-secret")
    return TestClient(app)


def _fail_if_called(*args, **kwargs):
    raise AssertionError("chat_turn must not be called")


def test_continuation_endpoint_skips_llm(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.main.chat_turn", _fail_if_called)
    with _client(tmp_path, monkeypatch) as client:
        project = client.post(
            "/api/projects",
            json={"name": "入力テスト", "initial_idea": "要件を順番に入力する"},
            headers=HEADERS,
        ).json()
        result = client.post(
            f"/api/projects/{project['id']}/messages",
            json={"content": "まだ続く。視認性を20点とする"},
            headers=HEADERS,
        )

    assert result.status_code == 200
    body = result.json()
    assert "まだAI解析は実行していません" in body["messages"][-1]["content"]
    assert "まだ続く。視認性を20点とする" in body["requirements"]["raw_notes"]


def test_unhelpful_yes_endpoint_skips_llm(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.main.chat_turn", _fail_if_called)
    with _client(tmp_path, monkeypatch) as client:
        project = client.post(
            "/api/projects",
            json={"name": "回答テスト", "initial_idea": "予約システム"},
            headers=HEADERS,
        ).json()
        result = client.post(
            f"/api/projects/{project['id']}/messages",
            json={"content": "はい"},
            headers=HEADERS,
        )

    assert result.status_code == 200
    body = result.json()
    assert "AI解析は実行していません" in body["messages"][-1]["content"]
    assert "誰のどんな問題" in body["messages"][-1]["content"]


def test_bootstrap_asks_only_one_question(tmp_path: Path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        project = client.post(
            "/api/projects",
            json={"name": "質問数テスト", "initial_idea": "顧客管理"},
            headers=HEADERS,
        ).json()

    assistant = project["messages"][-1]["content"]
    assert assistant.count("？") == 1


def test_paid_ai_choice_is_saved_without_calling_llm(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.main.chat_turn", _fail_if_called)
    with _client(tmp_path, monkeypatch) as client:
        project = client.post(
            "/api/projects",
            json={
                "name": "AI費用テスト",
                "initial_idea": "Claudeのトークン消費を削減するシステム",
            },
            headers=HEADERS,
        ).json()
        assert project["policy_question"]["code"] == "PAID_AI_USAGE"

        result = client.post(
            f"/api/projects/{project['id']}/messages",
            json={"content": "有料AIは使いません"},
            headers=HEADERS,
        )

    assert result.status_code == 200
    body = result.json()
    assert body["policy_question"] is None
    assert any("有料AI APIを使用しない" in item for item in body["requirements"]["constraints"])
    assert any(
        item["topic"] == "実行時の有料AI利用" and item["decision"] == "使用しない"
        for item in body["requirements"]["decisions"]
    )
    assert "ルール、OSS、ローカルモデル" in body["messages"][-1]["content"]


def test_design_does_not_advance_before_paid_ai_choice(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.main.chat_turn", _fail_if_called)
    with _client(tmp_path, monkeypatch) as client:
        project = client.post(
            "/api/projects",
            json={
                "name": "AI確認待ちテスト",
                "initial_idea": "Claudeのトークン消費を削減するシステム",
            },
            headers=HEADERS,
        ).json()
        result = client.post(
            f"/api/projects/{project['id']}/messages",
            json={"content": "画像を自動判定したいです"},
            headers=HEADERS,
        )

    assert result.status_code == 200
    body = result.json()
    assert "有料AIを使いますか" in body["messages"][-1]["content"]
    assert "画像を自動判定したいです" in body["requirements"]["raw_notes"]
