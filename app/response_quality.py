from __future__ import annotations

import re


DECLARED_COUNT_RE = re.compile(r"(?:以下の?|次の?)\s*([1-9１-９])\s*(?:点|つ|項目)")
LIST_ITEM_RE = re.compile(r"(?m)^\s*(?:[1-9][.)．、]|[①-⑨]|[-・])\s*")
QUESTION_RE = re.compile(r"[^\n。！？?]*[？?]")
REFERENCE_RE = re.compile(r"(?:以下|次の通り|次の点)")
FULLWIDTH_DIGITS = str.maketrans("１２３４５６７８９", "123456789")


def response_quality_issues(message: str) -> list[str]:
    issues: list[str] = []
    questions = QUESTION_RE.findall(message)
    if len(questions) > 1:
        issues.append("multiple_questions")

    declared = DECLARED_COUNT_RE.search(message)
    if declared:
        expected = int(declared.group(1).translate(FULLWIDTH_DIGITS))
        if len(LIST_ITEM_RE.findall(message)) < expected:
            issues.append("missing_list_items")

    reference = REFERENCE_RE.search(message)
    if reference:
        tail = message[reference.end():]
        if not LIST_ITEM_RE.search(tail) and len(tail.strip()) < 40:
            issues.append("dangling_reference")
    return issues


def normalize_assistant_message(message: str, next_questions: list[str]) -> str:
    """不完全な参照や複数質問を、再生成せず短い回答へ直す。"""
    clean = message.strip()
    issues = response_quality_issues(clean)
    if not issues and len(clean) <= 600:
        return clean

    first_question = (next_questions[:1] or QUESTION_RE.findall(clean)[:1])
    question = first_question[0].strip() if first_question else ""
    statements = QUESTION_RE.sub("", clean)
    statements = re.sub(r"(?:以下|次の通り|次の点).*$", "", statements, flags=re.DOTALL).strip()
    summary_match = re.match(r"^.{1,240}?[。！!]", statements, re.DOTALL)
    summary = summary_match.group(0).strip() if summary_match else statements[:240].strip()
    if not summary:
        summary = "要件を更新しました。"
    return f"{summary}\n\n{question}".strip()[:600]
