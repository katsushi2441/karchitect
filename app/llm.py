from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from . import rqdb4ai_client
from .config import LLM_TIMEOUT, OLLAMA_URL
from .models import ChatTurnOutput, Requirements
from .prompts import SYSTEM_PROMPT, build_turn_prompt


logger = logging.getLogger("karchitect.llm")

# 1ターンの出力上限。キュー経由でもワーカーへ同じ値を渡す。
NUM_PREDICT = 5000


class OllamaError(RuntimeError):
    pass


def _build_output(content: str, requirements: Requirements) -> ChatTurnOutput:
    """LLMの生応答を ChatTurnOutput にする。直叩きとキュー経由で共通。"""
    result = ChatTurnOutput.model_validate(_parse_json_content(content))
    result.requirements.revision = requirements.revision + 1
    return result


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
    schema = ChatTurnOutput.model_json_schema()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    # RQDB4AI のキューが設定されていればそちらを優先する。直叩き(0.3)は
    # kcbrain / kfreqaihl と GPU を奪い合い、混雑時に応答が返らなくなる。
    if rqdb4ai_client.configured():
        try:
            content, job_id = await rqdb4ai_client.run_ollama_chat(
                messages, model, schema, NUM_PREDICT
            )
            logger.info("LLM turn via RQDB4AI queue (job=%s)", job_id)
            return _build_output(content, requirements)
        except Exception as exc:
            # キューが落ちていても対話は続けたい。直叩きへ退避する。
            logger.warning(
                "RQDB4AI queue unavailable, falling back to direct Ollama: %s: %s",
                type(exc).__name__, str(exc)[:200],
            )

    payload = {
        "model": model,
        "stream": False,
        "think": False,
        "format": schema,
        "messages": messages,
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
            "num_predict": NUM_PREDICT,
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
    return _build_output(content, requirements)


async def health() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
        models = [item.get("name", "") for item in response.json().get("models", [])]
        return {"ok": True, "url": OLLAMA_URL, "models": models}
    except Exception as exc:
        return {"ok": False, "url": OLLAMA_URL, "error": str(exc)}

