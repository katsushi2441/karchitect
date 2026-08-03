from __future__ import annotations

import json
import os
from typing import Any

import requests

# RQDB4AI 経由の Ollama は 192.168.0.14 を使う（ワークスペース規約）。
# 直叩きの 192.168.0.3 と混同しないこと。
DEFAULT_OLLAMA_URL = "http://192.168.0.14:11434"
MAX_MESSAGES_CHARS = 200_000


def ollama_chat_job(
    messages: list[dict[str, str]],
    model: str = "gemma4:12b-it-qat",
    temperature: float = 0.2,
    top_p: float = 0.9,
    num_predict: int = 5000,
    response_format: Any = None,
    request_timeout: int = 900,
    source: str = "karchitect",
    **_: Any,
) -> dict[str, Any]:
    """RQDB4AI worker entrypoint for Kurage Architect's design conversation.

    kgeo.jobs.ollama_chat_job との違いは **構造化出力に対応している点**。
    karchitect は Ollama の `format` に JSON Schema を渡して ChatTurnOutput を
    受け取る設計なので、format を落とすと応答が自由文になり解析に失敗する。
    """
    if not isinstance(messages, list) or not messages:
        raise RuntimeError("messages are required")
    serialized = json.dumps(messages, ensure_ascii=False)
    if len(serialized) > MAX_MESSAGES_CHARS:
        raise RuntimeError(
            f"messages are too large ({len(serialized)} > {MAX_MESSAGES_CHARS})"
        )

    ollama_url = os.environ.get("KARCHITECT_WORKER_OLLAMA_URL", DEFAULT_OLLAMA_URL).rstrip("/")
    payload: dict[str, Any] = {
        "model": str(model),
        "messages": messages,
        "stream": False,
        # gemma4は思考型なので think:false が必須。付けないと隠れ推論トークンが
        # num_predict を食い潰し、response が空になる。
        "think": False,
        "options": {
            "temperature": float(temperature),
            "top_p": float(top_p),
            "num_predict": int(num_predict),
        },
    }
    if response_format is not None:
        payload["format"] = response_format

    response = requests.post(
        f"{ollama_url}/api/chat",
        json=payload,
        timeout=max(30, int(request_timeout)),
    )
    response.raise_for_status()
    body = response.json()
    text = str((body.get("message") or {}).get("content") or "").strip()
    if not text:
        raise RuntimeError(
            f"Ollama returned an empty response (done_reason={body.get('done_reason', 'unknown')})"
        )
    return {
        "ok": True,
        "status": "completed",
        "completion_scope": "business_result",
        "business_terminal": True,
        "items": 1,
        "response": text,
        "response_chars": len(text),
        "model": str(model),
        "source": source,
        "structured": response_format is not None,
        "ollama_host": "192.168.0.14",
        "note": "Kurage Architect design turn completed through the 0.14 Ollama queue",
    }
