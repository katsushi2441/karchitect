from __future__ import annotations

from .models import ChatTurnOutput, OpenQuestion, Requirements


DISCOVERY_QUESTIONS = [
    ("purpose", "このシステムで、誰のどんな問題を解決したいですか？"),
    ("target_users", "主な利用者は誰ですか？ 管理者や運用担当者も含めて教えてください。"),
    ("in_scope", "最初のリリースで必ず実現したい機能は何ですか？"),
    ("constraints", "期限、予算、既存システム、利用必須の技術などの制約はありますか？"),
]


def completeness(requirements: Requirements) -> int:
    checks = [
        bool(requirements.purpose or requirements.summary),
        bool(requirements.target_users),
        bool(requirements.in_scope),
        bool(requirements.functional_requirements),
        any(r.acceptance_criteria for r in requirements.functional_requirements),
        bool(requirements.non_functional_requirements),
        bool(requirements.data_entities),
        bool(requirements.architecture.backend or requirements.architecture.style),
        bool(requirements.functional_requirements)
        and not any(
            q.status == "open" and q.importance == "blocking"
            for q in requirements.open_questions
        ),
        bool(requirements.risks),
    ]
    coverage = round(sum(checks) / len(checks) * 100)
    stage_caps = {
        "discover": 20,
        "clarify": 45,
        "specify": 60,
        "plan": 75,
        "design": 88,
        "review": 96,
        "ready": 100,
    }
    return min(coverage, stage_caps[requirements.stage])


def bootstrap_message(requirements: Requirements) -> str:
    idea = requirements.summary.strip()
    intro = (
        f"「{idea[:120]}」について、実装できる設計書へ整理していきます。"
        if idea
        else "作りたいシステムについて、実装できる設計書へ整理していきます。"
    )
    return (
        f"{intro}\n\n"
        "まず、次の点を教えてください。\n"
        "1. このシステムで、誰のどんな問題を解決したいですか？\n"
        "2. 最初のリリースで必ず必要な機能は何ですか？"
    )


def fallback_turn(requirements: Requirements, user_message: str, warning: str) -> ChatTurnOutput:
    updated = requirements.model_copy(deep=True)
    if user_message not in updated.raw_notes:
        updated.raw_notes.append(user_message)
    updated.revision += 1
    questions: list[str] = []
    for field, question in DISCOVERY_QUESTIONS:
        value = getattr(updated, field)
        if not value:
            questions.append(question)
        if len(questions) == 2:
            break
    if not questions:
        questions = ["この要望の受入条件を、利用者が確認できる形で教えてください。"]
    existing = {item.question for item in updated.open_questions}
    for question in questions:
        if question not in existing:
            updated.open_questions.append(
                OpenQuestion(
                    id=f"Q{len(updated.open_questions) + 1:03d}",
                    question=question,
                    category="fallback",
                    importance="important",
                )
            )
    return ChatTurnOutput(
        assistant_message=(
            "ご回答は要件メモへ保存しました。現在ローカルLLMの構造化応答を利用できないため、"
            "情報を失わない形で継続しています。\n\n"
            + "\n".join(f"- {question}" for question in questions)
        ),
        requirements=updated,
        next_questions=questions,
        changed_summary=["ユーザー回答をraw_notesへ保存", warning],
    )
