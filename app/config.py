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
LLM_TIMEOUT = float(os.environ.get("KARCHITECT_LLM_TIMEOUT", "180"))
INTERNAL_TOKEN = os.environ.get("KARCHITECT_INTERNAL_TOKEN", "")
DEV_USER = os.environ.get("KARCHITECT_DEV_USER", "local")
