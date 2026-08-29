from __future__ import annotations

import asyncio
import hmac
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import ADMIN_USERS, DATA_DIR, DEFAULT_MODEL, DEV_USER, INTERNAL_TOKEN, STATIC_DIR
from .db import (
    add_message,
    create_project,
    get_messages,
    get_project,
    init_db,
    list_owners,
    list_projects,
    parse_requirements,
    save_project,
)
from .documents import build_markdown, render_html, render_pdf, requirements_json
from .engine import (
    PRESERVED_LIST_FIELDS,
    bootstrap_message,
    completeness,
    fallback_turn,
    next_action,
    preserve_existing_content,
)
from .input_guard import append_raw_note, classify_user_input, completion_body
from .llm import OllamaError, chat_turn, health as ollama_health
from .models import (
    MessageCreate,
    ProjectCreate,
    ProjectDetail,
    ProjectSummary,
    Requirements,
)
from .policies import (
    apply_policy_choice,
    design_policy_warnings,
    enforce_design_policies,
    next_policy_question,
    parse_policy_answer,
)

logger = logging.getLogger("karchitect")


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


def _valid_username(value: str) -> bool:
    return bool(value) and len(value) <= 200 and not any(ord(char) < 32 for char in value)


def is_admin(username: str) -> bool:
    return username in ADMIN_USERS


def authenticated_owner(
    x_karchitect_token: str = Header(default=""),
    x_karchitect_user: str = Header(default=""),
    x_karchitect_act_as: str = Header(default=""),
) -> str:
    """操作対象のオーナー。管理者だけ X-Karchitect-Act-As で代理操作できる。

    代理操作はテスターが詰まったときに運営が直接手当てするためのもの。
    管理者以外がヘッダを付けても無視せず 403 にする（黙って自分の
    データを操作すると、代理できたと誤解したまま作業が進む）。
    """
    if not INTERNAL_TOKEN:
        return DEV_USER
    if not x_karchitect_token or not hmac.compare_digest(
        x_karchitect_token.encode("utf-8"),
        INTERNAL_TOKEN.encode("utf-8"),
    ):
        raise HTTPException(status_code=401, detail="Invalid internal token")
    owner = x_karchitect_user.strip()
    if not _valid_username(owner):
        raise HTTPException(status_code=401, detail="Authenticated user is required")
    act_as = x_karchitect_act_as.strip()
    if not act_as or act_as == owner:
        return owner
    if not is_admin(owner):
        raise HTTPException(status_code=403, detail="代理操作は管理者のみ利用できます")
    if not _valid_username(act_as):
        raise HTTPException(status_code=400, detail="代理操作の対象ユーザーが不正です")
    logger.info("admin %s acting as %s", owner, act_as)
    return act_as


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
        design_warnings=design_policy_warnings(req),
        policy_question=next_policy_question(req),
        next_action=next_action(req),
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


@app.get("/api/admin/users")
def admin_users(
    x_karchitect_token: str = Header(default=""),
    x_karchitect_user: str = Header(default=""),
) -> dict:
    """代理操作の対象にできる利用者の一覧。管理者専用・読み取りのみ。"""
    if INTERNAL_TOKEN:
        if not x_karchitect_token or not hmac.compare_digest(
            x_karchitect_token.encode("utf-8"), INTERNAL_TOKEN.encode("utf-8")
        ):
            raise HTTPException(status_code=401, detail="Invalid internal token")
        requester = x_karchitect_user.strip()
        if not is_admin(requester):
            raise HTTPException(status_code=403, detail="管理者のみ利用できます")
    return {"users": list_owners()}


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
        content = payload.content.strip()
        decision = classify_user_input(content, req, history_models)
        add_message(owner, project_id, "user", content)

        if decision.action == "save_only":
            updated = append_raw_note(req, content)
            save_project(owner, project_id, updated, build_markdown(updated), llm_warning="")
            add_message(owner, project_id, "assistant", decision.response)
            logger.info("LLM skipped for continuation: owner=%s project=%s", owner, project_id)
            return _detail(owner, project_id)

        if decision.action in {"reject", "duplicate"}:
            add_message(owner, project_id, "assistant", decision.response)
            logger.info(
                "LLM skipped for %s input: owner=%s project=%s",
                decision.action, owner, project_id,
            )
            return _detail(owner, project_id)

        policy_question = next_policy_question(req)
        if policy_question is not None:
            policy_choice = parse_policy_answer(content, policy_question.code)
            if policy_choice in {"prohibited", "allowed"}:
                updated = apply_policy_choice(req, policy_question.code, policy_choice)
                if policy_question.code == "RUNTIME_AI_USAGE":
                    response = (
                        "実行時にAIを使わない方針を確定しました。ローカルモデルも使わず、"
                        "固定ルール、通常処理、担当者確認だけで設計します。"
                        if policy_choice == "prohibited"
                        else "実行時AIの利用を許可する方針を確定しました。利用箇所と実行方式も設計します。"
                    )
                else:
                    response = (
                        "有料の外部APIを使わない方針を確定しました。公開データ取込または"
                        "担当者入力で設計します。"
                        if policy_choice == "prohibited"
                        else "有料外部APIの利用を許可する方針を確定しました。利用箇所と費用上限も設計します。"
                    )
                following = next_policy_question(updated)
                if following is not None:
                    response += f"\n\n続けて確認します。{following.question}"
            else:
                note = completion_body(content) or content
                updated = append_raw_note(req, note) if note != "入力完了" else req
                response = (
                    "設計を進める前に確認が必要です。\n\n"
                    + policy_question.question
                )
            save_project(owner, project_id, updated, build_markdown(updated), llm_warning="")
            add_message(owner, project_id, "assistant", response)
            logger.info("LLM skipped for paid AI policy: owner=%s project=%s", owner, project_id)
            return _detail(owner, project_id)

        body = completion_body(content)
        if body:
            req = append_raw_note(req, body)
        warning = ""
        try:
            turn = await chat_turn(row["model"], req, history, content)
        except (OllamaError, ValueError, json.JSONDecodeError) as exc:
            warning = str(exc)
            # ログに残さないと障害に気づけない。2026-08-03にLLMタイムアウトで
            # 利用者の作業が止まったが、記録がDBのllm_warning列にしか無く、
            # サービスのログには何も出ていなかった。
            logger.warning(
                "LLM turn failed: owner=%s project=%s model=%s history=%d 文字数=%d: %s",
                owner, project_id, row["model"], len(history),
                len(content), warning,
            )
            turn = fallback_turn(req, content, warning)
        # LLMが出し忘れた項目で、確定済みの内容を消さない。
        turn.requirements = preserve_existing_content(req, turn.requirements)
        turn.requirements = enforce_design_policies(turn.requirements)
        dropped = [
            name
            for name in PRESERVED_LIST_FIELDS
            if (getattr(req, name, None) or []) and not (getattr(turn.requirements, name, None) or [])
        ]
        if dropped:  # 埋め戻し後も空なら異常。気づけるように残す
            logger.warning("requirements sections still empty after preserve: %s", dropped)
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
    # 再生成が成功した時点で、前回のLLM警告は事実ではなくなる。引き継ぐと
    # 解消済みのエラーが画面に出続ける(2026-08-03、利用者の画面に残り続けた)。
    save_project(owner, project_id, req, build_markdown(req), llm_warning="")
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
