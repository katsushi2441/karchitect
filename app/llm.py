from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .config import LLM_TIMEOUT, OLLAMA_URL
from .models import ChatTurnOutput, Requirements
from .prompts import SYSTEM_PROMPT, build_turn_prompt


class OllamaError(RuntimeError):
    pass


def _parse_json_content(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise OllamaError("Gemmaの応答にJSONが含まれていません")
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise OllamaError(f"GemmaのJSON応答を解析できません: {exc}") from exc


async def chat_turn(
    model: str,
    requirements: Requirements,
    history: list[dict[str, str]],
    user_message: str,
) -> ChatTurnOutput:
    prompt = build_turn_prompt(requirements.model_dump_json(indent=2), history, user_message)
    payload = {
        "model": model,
        "stream": False,
        "think": False,
        "format": ChatTurnOutput.model_json_schema(),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
            "num_predict": 5000,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            response = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        # httpx.ReadTimeout は str() が空になるため、そのまま埋め込むと
        # 「Ollamaへの接続に失敗しました: 」とだけ出て原因が分からない
        # (2026-08-03、実際にこれで切り分けが遅れた)。
        # GPUは1枚を他サービスと共有しているので、混雑時は待ち時間が延びる。
        raise OllamaError(
            f"AIの応答が{LLM_TIMEOUT:.0f}秒以内に返りませんでした"
            f"（{type(exc).__name__}）。GPUが混雑している可能性があります。"
            "少し待ってから、同じ内容をもう一度送信してください。"
        ) from exc
    except httpx.HTTPError as exc:
        raise OllamaError(f"Ollamaへの接続に失敗しました: {type(exc).__name__}: {exc}") from exc
    body = response.json()
    content = str((body.get("message") or {}).get("content") or "").strip()
    if not content:
        raise OllamaError(
            f"Gemmaから空の応答が返りました（done_reason={body.get('done_reason', 'unknown')}）"
        )
    result = ChatTurnOutput.model_validate(_parse_json_content(content))
    result.requirements.revision = requirements.revision + 1
    return result


async def health() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
        models = [item.get("name", "") for item in response.json().get("models", [])]
        return {"ok": True, "url": OLLAMA_URL, "models": models}
    except Exception as exc:
        return {"ok": False, "url": OLLAMA_URL, "error": str(exc)}

