from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
STATIC_DIR = ROOT / "static"
TEMPLATES_DIR = ROOT / "templates"

HOST = os.environ.get("KARCHITECT_HOST", "127.0.0.1")
PORT = int(os.environ.get("KARCHITECT_PORT", "18347"))
OLLAMA_URL = os.environ.get("KARCHITECT_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("KARCHITECT_MODEL", "gemma4:12b-it-qat")
DB_PATH = Path(os.environ.get("KARCHITECT_DB", DATA_DIR / "karchitect.db"))
LLM_TIMEOUT = float(os.environ.get("KARCHITECT_LLM_TIMEOUT", "900"))
# 1ターンの出力上限。requirements の全状態を毎回返させる設計なので、
# データが育つほど必要量が増える。フィールド詳細定義を持つようになり
# 5000 では再出力だけで枯渇していた(2026-08-03、実測で requirements_json が
# 既に 7,292 文字あり、応答本文が 186 文字まで痩せた)。
NUM_PREDICT = int(os.environ.get("KARCHITECT_NUM_PREDICT", "16000"))
INTERNAL_TOKEN = os.environ.get("KARCHITECT_INTERNAL_TOKEN", "")
DEV_USER = os.environ.get("KARCHITECT_DEV_USER", "local")

# 代理操作を許す管理者。テスターの詰まりを運営側で解消できるようにする。
ADMIN_USERS = tuple(
    u.strip()
    for u in (os.environ.get("KARCHITECT_ADMIN_USERS", "").strip() or "xb_bittensor").split(",")
    if u.strip()
)

# RQDB4AI のホスト別キュー経由で Ollama(192.168.0.14) を使う設定。
# 未設定なら OLLAMA_URL への直叩きにそのまま退避する。
RQDB4AI_URL = os.environ.get("KARCHITECT_RQDB4AI_URL", "").strip().rstrip("/")
RQDB4AI_TOKEN = os.environ.get("KARCHITECT_RQDB4AI_TOKEN", "").strip()
RQDB4AI_FUNCTION = (
    os.environ.get("KARCHITECT_RQDB4AI_FUNCTION", "").strip()
    or "karchitect.jobs.ollama_chat_job"
)
RQDB4AI_POLL_INTERVAL = max(0.5, float(os.environ.get("KARCHITECT_RQDB4AI_POLL_INTERVAL", "2")))
# 待ち行列に並ぶぶん直叩きより待たされる。LLM_TIMEOUT より長く取る。
RQDB4AI_WAIT_TIMEOUT = max(60.0, float(os.environ.get("KARCHITECT_RQDB4AI_WAIT_TIMEOUT", "1200")))
