"""RQDB4AI のホスト別キュー経由で Ollama を呼ぶクライアント。

直叩き(127.0.0.1 = 192.168.0.3)だと、kcbrain / kfreqaihl の判断ジョブと
GPU 1枚を奪い合う。2026-08-03 に利用者の設計セッションが最終成果物の生成中に
180秒でタイムアウトした際、同時間帯に /api/generate が8件走っていた。

RQDB4AI は ollama-192-168-0-14-web キューで直列化するため、待ち行列に並ぶ代わりに
競合による中断が起きない。キューが未設定・不達のときは直叩きへ退避する
(可用性を落とさない)。実装は kgeo/app/rqdb4ai_client.py に合わせている。
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from . import config


def configured() -> bool:
    return bool(config.RQDB4AI_URL and config.RQDB4AI_TOKEN and config.RQDB4AI_FUNCTION)


def enqueue_payload(
    messages: list[dict[str, str]],
    model: str,
    response_format: Any,
    num_predict: int,
) -> dict[str, Any]:
    request_timeout = int(config.LLM_TIMEOUT)
    return {
        # queue=auto は ollama_host と source から
        # ollama-192-168-0-14-web を選ぶ(rqdb4ai README の Resource Queues)。
        "queue": "auto",
        "function": config.RQDB4AI_FUNCTION,
        "kwargs": {
            "messages": messages,
            "model": model,
            "temperature": 0.2,
            "top_p": 0.9,
            "num_predict": num_predict,
            # 構造化出力。karchitect はこれが無いと応答を解析できない。
            "response_format": response_format,
            "request_timeout": request_timeout,
            "source": "karchitect",
        },
        "meta": {
            "project": "karchitect",
            "app": "karchitect",
            "kind": "ollama_chat",
            "resource": "ollama",
            "resource_key": f"ollama:192.168.0.14:{model}",
            "ollama_host": "192.168.0.14",
            "ollama_endpoint": "http://192.168.0.14:11434",
            "ollama_model": model,
            # 利用者が画面の前で待っている対話なので web(interactive) 側に入れる。
            "source": "web_online",
            "queue_class": "web",
            "priority_class": "interactive",
        },
        "timeout": request_timeout + 60,
        "result_ttl": 3600,
        "failure_ttl": 604800,
    }


def _headers() -> dict[str, str]:
    if not configured():
        raise RuntimeError("RQDB4AI Ollama queue is not configured")
    return {
        "Authorization": f"Bearer {config.RQDB4AI_TOKEN}",
        "Content-Type": "application/json",
    }


async def run_ollama_chat(
    messages: list[dict[str, str]],
    model: str,
    response_format: Any,
    num_predict: int,
) -> tuple[str, str]:
    """キューに投入し、実際の結果が返るまで待つ。戻り値は (本文, ジョブID)。"""
    timeout = httpx.Timeout(30.0, connect=10.0)
    headers = _headers()
    job_id = ""
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{config.RQDB4AI_URL}/api/enqueue",
            headers=headers,
            json=enqueue_payload(messages, model, response_format, num_predict),
        )
        response.raise_for_status()
        job_id = str((response.json().get("job") or {}).get("id") or "")
        if not job_id:
            raise RuntimeError("RQDB4AI enqueue returned no job id")

        deadline = asyncio.get_running_loop().time() + config.RQDB4AI_WAIT_TIMEOUT
        status = "queued"
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(config.RQDB4AI_POLL_INTERVAL)
            detail_response = await client.get(
                f"{config.RQDB4AI_URL}/api/jobs/{job_id}", headers=headers
            )
            detail_response.raise_for_status()
            detail = detail_response.json().get("job") or {}
            status = str(detail.get("status") or "unknown")
            if status == "finished":
                result_response = await client.get(
                    f"{config.RQDB4AI_URL}/api/jobs/{job_id}/result", headers=headers
                )
                result_response.raise_for_status()
                result = result_response.json().get("result")
                text = str((result or {}).get("response") or "").strip()
                if not isinstance(result, dict) or not result.get("ok") or not text:
                    raise RuntimeError(f"RQDB4AI returned an invalid Ollama result ({job_id})")
                return text, job_id
            if status in {"failed", "stopped", "canceled"}:
                error = detail.get("exc_info") or detail.get("error") or status
                raise RuntimeError(f"RQDB4AI Ollama job {job_id} {status}: {str(error)[:500]}")
    raise RuntimeError(f"RQDB4AI Ollama job timed out ({job_id}, status={status})")
