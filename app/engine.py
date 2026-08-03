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


# 完成度10項目のうち何が欠けているか。利用者は「何を言えば進むのか」を
# 知らない。2026-08-03、テスターが自力で製品の限界を突き止めるまで3往復
# 消耗した。次の一手を画面から提示するための材料をここで作る。
NEXT_STAGE = {
    "discover": "clarify",
    "clarify": "specify",
    "specify": "plan",
    "plan": "design",
    "design": "review",
    "review": "ready",
    "ready": None,
}


def checklist(req: Requirements) -> list[dict]:
    """完成度10項目の達成状況。**画面にそのまま出す**ための一覧。

    以前は未達項目だけをボタンで出していたが、完成度の中身が画面に無いため
    「リスクと対策」というボタンだけが唐突に現れて意味が通らなかった
    (2026-08-03の指摘)。判定根拠を先に見せる。
    """
    items = [
        ("purpose", "目的と概要", bool(req.purpose or req.summary),
         "このシステムの目的と概要を確定してください。"),
        ("target_users", "対象利用者", bool(req.target_users),
         "対象となる利用者を確定してください。"),
        ("in_scope", "対象範囲", bool(req.in_scope),
         "今回の対象範囲を確定してください。"),
        ("functional_requirements", "機能要件", bool(req.functional_requirements),
         "主要な機能要件を整理してください。"),
        ("acceptance_criteria", "受入条件",
         any(r.acceptance_criteria for r in req.functional_requirements),
         "各機能要件に検証可能な受入条件を付けてください。"),
        ("non_functional_requirements", "非機能要件", bool(req.non_functional_requirements),
         "性能・可用性・セキュリティなどの非機能要件を整理してください。"),
        ("data_entities", "データ設計", bool(req.data_entities),
         "データエンティティを整理してください。"),
        ("architecture", "システム構成",
         bool(req.architecture.backend or req.architecture.style),
         "システム構成（構成方式・基盤）を確定してください。"),
        ("blocking", "未決事項の解消",
         bool(req.functional_requirements) and not any(
             q.status == "open" and q.importance == "blocking" for q in req.open_questions
         ),
         "blockingな未決事項を解消してください。"),
        ("risks", "リスクと対策", bool(req.risks),
         "想定されるリスクと対策を洗い出してください。"),
    ]
    return [
        {"key": key, "label": label, "done": bool(done), "prompt": prompt}
        for key, label, done, prompt in items
    ]


def missing_items(req: Requirements) -> list[dict]:
    """埋まっていない完成度項目だけ。"""
    return [item for item in checklist(req) if not item["done"]]


def next_action(req: Requirements) -> dict:
    """画面に出す「次にやること」。工程を進める操作も文言つきで返す。"""
    missing = missing_items(req)
    nxt = NEXT_STAGE.get(req.stage)
    advance = None
    if nxt and not missing:
        advance = {
            "stage": nxt,
            "label": f"{nxt} に進む",
            "prompt": f"要件は出揃いました。{nxt} 工程へ進めてください。",
        }
    elif nxt and len(missing) <= 2:
        # 残りわずかなら、埋めつつ次工程へ進む提案も出す
        advance = {
            "stage": nxt,
            "label": f"{nxt} に進む",
            "prompt": f"残りの項目を整理して、{nxt} 工程へ進めてください。",
        }
    return {
        "checklist": checklist(req),
        "missing": missing,
        "advance": advance,
        "stage": req.stage,
        "next_stage": nxt,
    }
