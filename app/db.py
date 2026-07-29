from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import DB_PATH, DEFAULT_MODEL
from .models import Message, ProjectCreate, Requirements, now_iso


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL DEFAULT 'local',
    name TEXT NOT NULL,
    initial_idea TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL,
    stage TEXT NOT NULL,
    requirements_json TEXT NOT NULL,
    document_markdown TEXT NOT NULL DEFAULT '',
    llm_warning TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_project ON messages(project_id, id);
"""


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
        if "owner" not in columns:
            conn.execute("ALTER TABLE projects ADD COLUMN owner TEXT NOT NULL DEFAULT 'local'")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_projects_owner_updated "
            "ON projects(owner, updated_at DESC)"
        )


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_project(owner: str, payload: ProjectCreate) -> dict:
    project_id = uuid.uuid4().hex[:12]
    created = now_iso()
    requirements = Requirements(
        project_name=payload.name,
        summary=payload.initial_idea.strip(),
        raw_notes=[payload.initial_idea.strip()] if payload.initial_idea.strip() else [],
    )
    model = payload.model.strip() or DEFAULT_MODEL
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO projects
                (id, owner, name, initial_idea, model, stage, requirements_json,
                 document_markdown, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, '', ?, ?)
            """,
            (
                project_id,
                owner,
                payload.name.strip(),
                payload.initial_idea.strip(),
                model,
                requirements.stage,
                requirements.model_dump_json(),
                created,
                created,
            ),
        )
    return get_project(owner, project_id)


def list_projects(owner: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM projects WHERE owner = ? ORDER BY updated_at DESC",
            (owner,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_project(owner: str, project_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ? AND owner = ?",
            (project_id, owner),
        ).fetchone()
    return dict(row) if row else None


def save_project(
    owner: str,
    project_id: str,
    requirements: Requirements,
    document_markdown: str,
    *,
    llm_warning: str = "",
) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE projects
            SET name = ?, stage = ?, requirements_json = ?, document_markdown = ?,
                llm_warning = ?, updated_at = ?
            WHERE id = ? AND owner = ?
            """,
            (
                requirements.project_name or "名称未定",
                requirements.stage,
                requirements.model_dump_json(),
                document_markdown,
                llm_warning,
                now_iso(),
                project_id,
                owner,
            ),
        )


def add_message(owner: str, project_id: str, role: str, content: str) -> Message:
    created = now_iso()
    with connect() as conn:
        exists = conn.execute(
            "SELECT 1 FROM projects WHERE id = ? AND owner = ?",
            (project_id, owner),
        ).fetchone()
        if not exists:
            raise KeyError("Project not found")
        cursor = conn.execute(
            "INSERT INTO messages (project_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (project_id, role, content, created),
        )
        message_id = int(cursor.lastrowid)
    return Message(id=message_id, role=role, content=content, created_at=created)


def get_messages(owner: str, project_id: str, limit: int = 100) -> list[Message]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM (
                SELECT id, role, content, created_at
                FROM messages
                WHERE project_id = ?
                  AND EXISTS (
                    SELECT 1 FROM projects
                    WHERE projects.id = messages.project_id AND projects.owner = ?
                  )
                ORDER BY id DESC LIMIT ?
            ) ORDER BY id
            """,
            (project_id, owner, limit),
        ).fetchall()
    return [Message.model_validate(dict(row)) for row in rows]


def parse_requirements(project: dict) -> Requirements:
    return Requirements.model_validate(json.loads(project["requirements_json"]))
