from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .models import Message, Requirements


InputAction = Literal["llm", "save_only", "reject", "duplicate"]


@dataclass(frozen=True)
class InputDecision:
    action: InputAction
    response: str = ""
    pending_question: str = ""


CONTINUATION_RE = re.compile(
    r"^\s*(?:まだ続く|まだ入力中|続き(?:です|ます)?|入力中|続けます)(?:[\s。．、,:：]|$)",
    re.IGNORECASE,
)
COMPLETION_RE = re.compile(
    r"(?:^|\n\s*|(?<=[。．])\s*)(?:入力完了|以上です|これで終わり|ここまでです)\s*[。．]?\s*$",
    re.IGNORECASE,
)
SHORT_YES = {"はい", "はい。", "yes", "ok", "okay", "そうです", "その通り", "同意します"}
SHORT_NO = {"いいえ", "いいえ。", "no", "ありません", "特にありません"}
GENERIC_SHORT = SHORT_YES | SHORT_NO | {"了解", "わかりました", "うん", "そう", "任せます"}
CONFIRMATION_RE = re.compile(
    r"(?:よろしい|合っています|合ってます|認識で|理解で|ということで|進めますか|"
    r"採用しますか|利用しますか|必要ですか|確定しますか)"
)
EXISTENCE_RE = re.compile(r"(?:ありますか|いますか|ございますか)")


def is_continuation(content: str) -> bool:
    return bool(CONTINUATION_RE.search(content))


def is_completion(content: str) -> bool:
    return bool(COMPLETION_RE.search(content))


def completion_body(content: str) -> str:
    """「入力完了」と同時に送られた本文だけを返す。"""
    return COMPLETION_RE.sub("", content).strip()


def _latest_questions(messages: list[Message]) -> list[str]:
    for message in reversed(messages):
        if message.role != "assistant":
            continue
        questions = [
            item.strip()
            for item in re.findall(r"[^\n。！？?]*[？?]", message.content)
            if item.strip()
        ]
        if questions:
            return questions
    return []


def _normalized(content: str) -> str:
    return re.sub(r"\s+", "", content).casefold()


def _is_duplicate(content: str, messages: list[Message]) -> bool:
    current = _normalized(content)
    recent_user = [item for item in messages[-8:] if item.role == "user"]
    return any(_normalized(item.content) == current for item in recent_user)


def _short_answer_is_valid(content: str, questions: list[str]) -> bool:
    if len(questions) != 1:
        return False
    answer = content.strip().casefold()
    question = questions[0]
    if answer in SHORT_YES:
        return bool(CONFIRMATION_RE.search(question))
    if answer in SHORT_NO:
        return bool(CONFIRMATION_RE.search(question) or EXISTENCE_RE.search(question))
    return False


def classify_user_input(
    content: str,
    requirements: Requirements,
    messages: list[Message],
) -> InputDecision:
    """LLMを呼ぶ価値がある入力かを、GPUを使わず判定する。"""
    clean = content.strip()
    if is_completion(clean):
        return InputDecision(action="llm")
    if is_continuation(clean):
        return InputDecision(
            action="save_only",
            response=(
                "続きとして保存しました。まだAI解析は実行していません。"
                "入力が終わったら「入力完了・解析」を押してください。"
            ),
        )
    if _is_duplicate(clean, messages):
        return InputDecision(
            action="duplicate",
            response="同じ内容が直近に保存済みのため、AI解析は実行しませんでした。",
        )

    questions = _latest_questions(messages)
    pending = questions[0] if len(questions) == 1 else ""
    normalized = clean.casefold()
    if normalized in GENERIC_SHORT and _short_answer_is_valid(clean, questions):
        return InputDecision(action="llm", pending_question=pending)
    if normalized in GENERIC_SHORT:
        if len(questions) > 1:
            reason = "未回答の質問が複数あるため、「はい」だけでは対象を判断できません。"
        elif pending:
            reason = "この質問には具体的な内容が必要です。"
        else:
            reason = "「はい」だけでは設計要件を更新できません。"
        return InputDecision(
            action="reject",
            response=(
                f"{reason}AI解析は実行していません。"
                + (f"\n\n回答してほしい質問: {pending}" if pending else "")
            ),
            pending_question=pending,
        )
    if len(_normalized(clean)) < 4:
        return InputDecision(
            action="reject",
            response=(
                "回答が短すぎて要件を更新できないため、AI解析は実行していません。"
                + (f"\n\n回答してほしい質問: {pending}" if pending else "")
            ),
            pending_question=pending,
        )
    return InputDecision(action="llm", pending_question=pending)


def append_raw_note(requirements: Requirements, content: str) -> Requirements:
    updated = requirements.model_copy(deep=True)
    clean = content.strip()
    if clean and clean not in updated.raw_notes:
        updated.raw_notes.append(clean)
        updated.revision += 1
    return updated
