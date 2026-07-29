from __future__ import annotations

import asyncio
import hmac
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import DATA_DIR, DEFAULT_MODEL, DEV_USER, INTERNAL_TOKEN, STATIC_DIR
from .db import (
    add_message,
    create_project,
    get_messages,
    get_project,
    init_db,
    list_projects,
    parse_requirements,
    save_project,
)
from .documents import build_markdown, render_html, render_pdf, requirements_json
from .engine import bootstrap_message, completeness, fallback_turn
from .llm import OllamaError, chat_turn, health as ollama_health
from .models import (
    MessageCreate,
    ProjectCreate,
    ProjectDetail,
    ProjectSummary,
    Requirements,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Kurage Architect API",
    description="Conversational system design studio powered by local Gemma",
    version=__version__,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
project_locks: dict[str, asyncio.Lock] = {}


def authenticated_owner(
    x_karchitect_token: str = Header(default=""),
    x_karchitect_user: str = Header(default=""),
) -> str:
    if INTERNAL_TOKEN:
        if not x_karchitect_token or not hmac.compare_digest(
            x_karchitect_token.encode("utf-8"),
            INTERNAL_TOKEN.encode("utf-8"),
        ):
            raise HTTPException(status_code=401, detail="Invalid internal token")
        owner = x_karchitect_user.strip()
        if not owner or len(owner) > 200 or any(ord(char) < 32 for char in owner):
            raise HTTPException(status_code=401, detail="Authenticated user is required")
        return owner
    return DEV_USER


def _row_summary(row: dict) -> ProjectSummary:
    req = parse_requirements(row)
    return ProjectSummary(
        id=row["id"],
        name=row["name"],
        stage=req.stage,
        completeness=completeness(req),
        model=row["model"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _detail(owner: str, project_id: str) -> ProjectDetail:
    row = get_project(owner, project_id)
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    req = parse_requirements(row)
    return ProjectDetail(
        **_row_summary(row).model_dump(),
        initial_idea=row["initial_idea"],
        requirements=req,
        messages=get_messages(owner, project_id),
        document_markdown=row["document_markdown"],
        llm_warning=row["llm_warning"],
    )


@app.get("/", response_class=FileResponse)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health(owner: str = Depends(authenticated_owner)) -> dict:
    ollama = await ollama_health()
    return {
        "ok": True,
        "service": "karchitect",
        "version": __version__,
        "default_model": DEFAULT_MODEL,
        "ollama": ollama,
        "authenticated": bool(owner),
    }


@app.get("/api/projects", response_model=list[ProjectSummary])
def projects(owner: str = Depends(authenticated_owner)) -> list[ProjectSummary]:
    return [_row_summary(row) for row in list_projects(owner)]


@app.post("/api/projects", response_model=ProjectDetail)
def new_project(
    payload: ProjectCreate,
    owner: str = Depends(authenticated_owner),
) -> ProjectDetail:
    row = create_project(owner, payload)
    req = parse_requirements(row)
    document = build_markdown(req)
    save_project(owner, row["id"], req, document)
    add_message(owner, row["id"], "assistant", bootstrap_message(req))
    return _detail(owner, row["id"])


@app.get("/api/projects/{project_id}", response_model=ProjectDetail)
def project(project_id: str, owner: str = Depends(authenticated_owner)) -> ProjectDetail:
    return _detail(owner, project_id)


@app.put("/api/projects/{project_id}/requirements", response_model=ProjectDetail)
def replace_requirements(
    project_id: str,
    requirements: Requirements,
    owner: str = Depends(authenticated_owner),
) -> ProjectDetail:
    row = get_project(owner, project_id)
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    requirements.revision = max(requirements.revision, parse_requirements(row).revision + 1)
    document = build_markdown(requirements)
    save_project(owner, project_id, requirements, document)
    add_message(owner, project_id, "system", "要件JSONが手動更新されました。")
    return _detail(owner, project_id)


@app.post("/api/projects/{project_id}/messages", response_model=ProjectDetail)
async def send_message(
    project_id: str,
    payload: MessageCreate,
    owner: str = Depends(authenticated_owner),
) -> ProjectDetail:
    lock = project_locks.setdefault(f"{owner}:{project_id}", asyncio.Lock())
    async with lock:
        row = get_project(owner, project_id)
        if not row:
            raise HTTPException(status_code=404, detail="Project not found")
        req = parse_requirements(row)
        history_models = get_messages(owner, project_id, limit=30)
        history = [{"role": message.role, "content": message.content} for message in history_models]
        add_message(owner, project_id, "user", payload.content.strip())
        warning = ""
        try:
            turn = await chat_turn(row["model"], req, history, payload.content.strip())
        except (OllamaError, ValueError, json.JSONDecodeError) as exc:
            warning = str(exc)
            turn = fallback_turn(req, payload.content.strip(), warning)
        document = build_markdown(turn.requirements)
        save_project(owner, project_id, turn.requirements, document, llm_warning=warning)
        add_message(owner, project_id, "assistant", turn.assistant_message)
        return _detail(owner, project_id)


@app.post("/api/projects/{project_id}/regenerate", response_model=ProjectDetail)
def regenerate(
    project_id: str,
    owner: str = Depends(authenticated_owner),
) -> ProjectDetail:
    row = get_project(owner, project_id)
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    req = parse_requirements(row)
    save_project(owner, project_id, req, build_markdown(req), llm_warning=row["llm_warning"])
    return _detail(owner, project_id)


@app.get("/api/projects/{project_id}/document.md", response_class=PlainTextResponse)
def document_markdown(
    project_id: str,
    owner: str = Depends(authenticated_owner),
) -> PlainTextResponse:
    row = get_project(owner, project_id)
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return PlainTextResponse(
        row["document_markdown"],
        headers={"Content-Disposition": f'attachment; filename="{project_id}-system-design.md"'},
    )


@app.get("/api/projects/{project_id}/requirements.json")
def document_json(
    project_id: str,
    owner: str = Depends(authenticated_owner),
) -> JSONResponse:
    row = get_project(owner, project_id)
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    req = parse_requirements(row)
    return JSONResponse(
        req.model_dump(mode="json"),
        headers={"Content-Disposition": f'attachment; filename="{project_id}-requirements.json"'},
    )


@app.get("/api/projects/{project_id}/document.html", response_class=HTMLResponse)
def document_html(
    project_id: str,
    owner: str = Depends(authenticated_owner),
) -> HTMLResponse:
    row = get_project(owner, project_id)
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return HTMLResponse(render_html(row["document_markdown"], row["name"]))


@app.get("/api/projects/{project_id}/document.pdf", response_class=FileResponse)
def document_pdf(
    project_id: str,
    owner: str = Depends(authenticated_owner),
) -> FileResponse:
    row = get_project(owner, project_id)
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    export = DATA_DIR / "exports" / f"{project_id}-system-design.pdf"
    render_pdf(row["document_markdown"], row["name"], export)
    return FileResponse(
        export,
        media_type="application/pdf",
        filename=f"{project_id}-system-design.pdf",
    )


@app.get("/api/projects/{project_id}/mermaid/{diagram}", response_class=PlainTextResponse)
def mermaid_source(
    project_id: str,
    diagram: str,
    owner: str = Depends(authenticated_owner),
) -> PlainTextResponse:
    if diagram not in {"architecture", "class", "sequence"}:
        raise HTTPException(status_code=404, detail="Unknown diagram")
    row = get_project(owner, project_id)
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    blocks = re_mermaid_blocks(row["document_markdown"])
    indexes = {"architecture": 0, "class": 1, "sequence": 2}
    index = indexes[diagram]
    if len(blocks) <= index:
        raise HTTPException(status_code=404, detail="Diagram not found")
    return PlainTextResponse(
        blocks[index],
        headers={"Content-Disposition": f'attachment; filename="{project_id}-{diagram}.mmd"'},
    )


def re_mermaid_blocks(markdown_text: str) -> list[str]:
    import re

    return [block.strip() for block in re.findall(r"```mermaid\s*(.*?)```", markdown_text, re.DOTALL)]
