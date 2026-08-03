"""RQDB4AIキュー経由のLLM呼び出しに関するテスト。"""

from __future__ import annotations

import pytest

from app import config, rqdb4ai_client
from karchitect.jobs import ollama_chat_job

SCHEMA = {"type": "object", "properties": {"assistant_message": {"type": "string"}}}


def test_enqueue_payload_targets_the_0_14_web_queue():
    """直叩き(0.3)ではなく、rqdb4aiが直列化する0.14のwebキューへ入れる。"""
    payload = rqdb4ai_client.enqueue_payload(
        [{"role": "user", "content": "hi"}], "gemma4:12b-it-qat", SCHEMA, 5000
    )
    assert payload["queue"] == "auto"
    assert payload["function"] == "karchitect.jobs.ollama_chat_job"
    # queue=auto は ollama_host と source からキュー名を決める
    assert payload["meta"]["ollama_host"] == "192.168.0.14"
    assert payload["meta"]["source"] == "web_online"
    assert payload["meta"]["queue_class"] == "web"


def test_enqueue_payload_carries_the_json_schema():
    """構造化出力を落とすと応答が自由文になり解析に失敗するため必ず渡す。"""
    payload = rqdb4ai_client.enqueue_payload(
        [{"role": "user", "content": "hi"}], "gemma4:12b-it-qat", SCHEMA, 5000
    )
    assert payload["kwargs"]["response_format"] == SCHEMA
    assert payload["kwargs"]["num_predict"] == 5000
    # ジョブのタイムアウトは待ち時間より長く取る
    assert payload["timeout"] > int(config.LLM_TIMEOUT)


def test_configured_requires_url_and_token(monkeypatch):
    monkeypatch.setattr(config, "RQDB4AI_URL", "")
    assert rqdb4ai_client.configured() is False
    monkeypatch.setattr(config, "RQDB4AI_URL", "http://127.0.0.1:18300")
    monkeypatch.setattr(config, "RQDB4AI_TOKEN", "")
    assert rqdb4ai_client.configured() is False
    monkeypatch.setattr(config, "RQDB4AI_TOKEN", "t")
    monkeypatch.setattr(config, "RQDB4AI_FUNCTION", "karchitect.jobs.ollama_chat_job")
    assert rqdb4ai_client.configured() is True


def test_worker_job_sends_format_and_disables_thinking(monkeypatch):
    """gemma4は思考型。think:false を落とすと response が空になる。"""
    captured = {}

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": '{"assistant_message":"ok"}'}}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr("karchitect.jobs.requests.post", fake_post)
    result = ollama_chat_job(
        [{"role": "user", "content": "hi"}], response_format=SCHEMA
    )
    assert result["ok"] is True
    assert result["structured"] is True
    assert captured["json"]["format"] == SCHEMA
    assert captured["json"]["think"] is False
    assert "192.168.0.14" in captured["url"]


def test_worker_job_rejects_empty_messages():
    with pytest.raises(RuntimeError, match="messages are required"):
        ollama_chat_job([])


def test_worker_job_rejects_empty_response(monkeypatch):
    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": "  "}, "done_reason": "length"}

    monkeypatch.setattr("karchitect.jobs.requests.post", lambda *a, **k: _Resp())
    with pytest.raises(RuntimeError, match="empty response"):
        ollama_chat_job([{"role": "user", "content": "hi"}])
