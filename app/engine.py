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


# 以前に確定した内容を、1回のLLMターンで失わないための保護。
# 2026-08-03、data_entities 5件がLLMの1応答で空配列になり、利用者の
# データモデルが設計書ごと消えた。プロンプトで「勝手に削除しない」と
# 指示していても構造化出力では守られないことがあるため、コード側で担保する。
PRESERVED_LIST_FIELDS = (
    "data_entities",
    "functional_requirements",
    "non_functional_requirements",
    "integrations",
    "decisions",
    "user_stories",
    "target_users",
    "in_scope",
    "out_of_scope",
    "constraints",
    "assumptions",
    "risks",
    "raw_notes",
)


def preserve_existing_content(previous: Requirements, incoming: Requirements) -> Requirements:
    """空になった項目を前回の内容で埋め戻す。

    「空にする」意図的な操作と「LLMが出し忘れた」事故は区別できないが、
    設計書を育てる製品では**失うほうが致命的**なので、埋め戻す側に倒す。
    削除したい場合は要件JSONの手動更新(PUT /requirements)で行える。
    """
    for name in PRESERVED_LIST_FIELDS:
        before = getattr(previous, name, None) or []
        after = getattr(incoming, name, None) or []
        if before and not after:
            setattr(incoming, name, before)
    return incoming
