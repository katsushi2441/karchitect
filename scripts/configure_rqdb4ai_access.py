#!/usr/bin/env python3
"""Kurage Architect 専用の RQDB4AI operate トークンを用意する（値は出力しない）。

kgeo/scripts/configure_rqdb4ai_access.py と同じ方式。RQDB4AI は operate ロールの
enqueue を関数の許可リストで制限しているため、トークンを持っているだけでは
403 になる。関数名を RQDB4AI_OPERATE_ENQUEUE_FUNCTIONS へ追加する必要がある。

実行後は rqdb4ai-api / rqdb4ai-web-worker / karchitect を再起動する。
"""

from __future__ import annotations

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KARCHITECT_ENV = ROOT / ".env"
RQDB_ENV = ROOT.parent / "rqdb4ai" / "rqdb4ai.env"
RQDB_WORKER_LAUNCHER = ROOT.parent / "rqdb4ai" / "run_worker_with_aixec_env.sh"
FUNCTION = "karchitect.jobs.ollama_chat_job"
KARCHITECT_PYTHONPATH = "/home/kojima/work/karchitect"


def read_env(path: Path) -> tuple[list[str], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    values: dict[str, str] = {}
    for line in lines:
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return lines, values


def update_env(path: Path, changes: dict[str, str]) -> None:
    lines, _ = read_env(path)
    pending = dict(changes)
    updated: list[str] = []
    for line in lines:
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in pending:
                updated.append(f"{key}={pending.pop(key)}")
                continue
        updated.append(line)
    if pending:
        if updated and updated[-1]:
            updated.append("")
        updated.extend(f"{key}={value}" for key, value in pending.items())
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    path.chmod(0o600)


def add_csv(existing: str, value: str) -> str:
    items = [item.strip() for item in existing.split(",") if item.strip()]
    if value not in items:
        items.append(value)
    return ",".join(items)


def main() -> int:
    if not KARCHITECT_ENV.is_file() or not RQDB_ENV.is_file():
        raise SystemExit("Kurage Architect or RQDB4AI environment file is missing")
    _, karchitect = read_env(KARCHITECT_ENV)
    _, rqdb = read_env(RQDB_ENV)
    token = karchitect.get("KARCHITECT_RQDB4AI_TOKEN", "")
    if len(token) < 32:
        token = secrets.token_hex(32)
    update_env(
        KARCHITECT_ENV,
        {
            "KARCHITECT_RQDB4AI_URL": "http://127.0.0.1:18300",
            "KARCHITECT_RQDB4AI_TOKEN": token,
            "KARCHITECT_RQDB4AI_FUNCTION": FUNCTION,
            "KARCHITECT_RQDB4AI_POLL_INTERVAL": "2",
            "KARCHITECT_RQDB4AI_WAIT_TIMEOUT": "1200",
        },
    )
    update_env(
        RQDB_ENV,
        {
            "RQDB4AI_OPERATE_TOKEN": add_csv(rqdb.get("RQDB4AI_OPERATE_TOKEN", ""), token),
            "RQDB4AI_OPERATE_ENQUEUE_FUNCTIONS": add_csv(
                rqdb.get("RQDB4AI_OPERATE_ENQUEUE_FUNCTIONS", ""), FUNCTION
            ),
        },
    )
    if RQDB_WORKER_LAUNCHER.is_file():
        launcher = RQDB_WORKER_LAUNCHER.read_text(encoding="utf-8")
        if KARCHITECT_PYTHONPATH not in launcher:
            updated = launcher.replace(":/tmp", f":{KARCHITECT_PYTHONPATH}:/tmp", 1)
            if updated == launcher:
                raise SystemExit("RQDB4AI worker PYTHONPATH could not be updated")
            RQDB_WORKER_LAUNCHER.write_text(updated, encoding="utf-8")
            RQDB_WORKER_LAUNCHER.chmod(0o755)
    print("Dedicated Kurage Architect RQDB4AI access configured (token hidden).")
    print("Restart rqdb4ai-api.service, rqdb4ai-web-worker.service and karchitect.service.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
