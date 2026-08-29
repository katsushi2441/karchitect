from __future__ import annotations

import re
from typing import Literal

from .models import Decision, DesignWarning, PolicyOption, PolicyQuestion, Requirements


AI_TERMS = re.compile(
    r"(?:LLM|VLM|AI解析|AI判定|生成AI|Claude|ChatGPT|OpenAI|Gemini|GPT)",
    re.IGNORECASE,
)
EXTERNAL_AI_TERMS = re.compile(
    r"(?:Claude|ChatGPT|OpenAI|Gemini|外部LLM|外部VLM|有料LLM|有料API)",
    re.IGNORECASE,
)
LOCAL_MARKERS = re.compile(
    r"(?:ローカル|オンプレ|自社サーバ|OSS|Ollama|無課金|オフライン)",
    re.IGNORECASE,
)
REDUCTION_TERMS = re.compile(
    r"(?:抑え|削減|減ら|節約|回避|依存しない|使わない|高コスト|大量に消費)",
    re.IGNORECASE,
)
PaidAIChoice = Literal["unknown", "prohibited", "allowed"]
PAID_AI_TOPIC = "実行時の有料AI利用"
PAID_AI_QUESTION = "このシステムの運用時に、Claudeなどの有料AIを使いますか？"
PROHIBIT_ANSWER_RE = re.compile(
    r"(?:有料AI|外部LLM|有料API).*(?:使わない|使いません|使用しない|禁止|不要)|"
    r"(?:使わない|使いません|使用しない).*(?:有料AI|外部LLM|有料API)",
    re.IGNORECASE,
)
ALLOW_ANSWER_RE = re.compile(
    r"(?:有料AI|外部LLM|有料API).*(?:使います|使用する|利用を許可|利用可)|"
    r"(?:使います|使用する|利用を許可).*(?:有料AI|外部LLM|有料API)",
    re.IGNORECASE,
)


def _goal_text(req: Requirements) -> str:
    return "\n".join(
        [req.summary, req.purpose, req.background, *req.raw_notes]
    )


def minimizes_external_ai(req: Requirements) -> bool:
    """外部AIの費用・トークン削減がプロジェクト目的かを判定する。"""
    text = _goal_text(req)
    has_ai_cost_subject = bool(
        re.search(r"(?:トークン|Claude|ChatGPT|OpenAI|外部LLM|LLM.*(?:費用|コスト))", text, re.I)
    )
    return has_ai_cost_subject and bool(REDUCTION_TERMS.search(text))


def _runtime_ai_statements(req: Requirements) -> list[str]:
    statements = [*req.assumptions, *req.constraints]
    for item in req.functional_requirements:
        statements.extend([item.title, item.description, *item.acceptance_criteria])
    for item in req.non_functional_requirements:
        statements.extend([item.requirement, item.target])
    for item in req.integrations:
        statements.extend([item.name, item.purpose, item.protocol])
    statements.extend(req.architecture.model_dump().values())
    return [
        text.strip()
        for text in statements
        if text and AI_TERMS.search(text) and not PROHIBIT_ANSWER_RE.search(text)
    ]


def paid_ai_choice(req: Requirements) -> PaidAIChoice:
    """明示的に確定した決定・制約だけを利用する。目的文から勝手に推測しない。"""
    for item in reversed(req.decisions):
        if item.topic != PAID_AI_TOPIC or item.status != "confirmed":
            continue
        if re.search(r"(?:使用しない|使わない|禁止)", item.decision):
            return "prohibited"
        if re.search(r"(?:使用する|利用を許可|利用可)", item.decision):
            return "allowed"
    joined = "\n".join(req.constraints)
    if PROHIBIT_ANSWER_RE.search(joined):
        return "prohibited"
    if ALLOW_ANSWER_RE.search(joined):
        return "allowed"
    return "unknown"


def needs_paid_ai_confirmation(req: Requirements) -> bool:
    return (
        paid_ai_choice(req) == "unknown"
        and (minimizes_external_ai(req) or bool(_runtime_ai_statements(req)))
    )


def paid_ai_policy_question(req: Requirements) -> PolicyQuestion | None:
    if not needs_paid_ai_confirmation(req):
        return None
    return PolicyQuestion(
        code="PAID_AI_USAGE",
        question=PAID_AI_QUESTION,
        options=[
            PolicyOption(
                label="使わない",
                value="有料AIは使いません",
                description="ルール、OSS、ローカルモデルだけで設計します。",
            ),
            PolicyOption(
                label="利用を許可",
                value="有料AIの利用を許可します",
                description="利用箇所と費用上限を設計します。",
            ),
        ],
    )


def parse_paid_ai_answer(content: str) -> PaidAIChoice:
    if PROHIBIT_ANSWER_RE.search(content):
        return "prohibited"
    if ALLOW_ANSWER_RE.search(content):
        return "allowed"
    return "unknown"


def _next_decision_id(req: Requirements) -> str:
    used = {item.id for item in req.decisions}
    number = len(used) + 1
    while f"D{number:03d}" in used:
        number += 1
    return f"D{number:03d}"


def _localize_ai_text(text: str) -> str:
    """有料・実行場所未定のAI名を、禁止方針に沿う表現へ置き換える。"""
    replacements = (
        (r"Claude|ChatGPT|OpenAI|Gemini|GPT", "ローカルモデル"),
        (r"外部LLM|有料LLM|有料API", "ローカルモデル"),
        (r"(?<!ローカル)LLM", "ローカルモデル"),
        (r"(?<!ローカル)VLM", "ローカルVLM"),
        (r"(?<!ローカル)AI解析", "ローカル画像解析"),
        (r"(?<!ローカル)AI判定", "ローカルモデル判定"),
        (r"(?<!ローカル)生成AI", "ローカル生成モデル"),
    )
    updated = text
    for pattern, replacement in replacements:
        updated = re.sub(pattern, replacement, updated, flags=re.IGNORECASE)
    return updated


def enforce_paid_ai_prohibition(req: Requirements) -> Requirements:
    """禁止確定後に、外部・実行場所未定のAI仮定を設計から除外する。"""
    if paid_ai_choice(req) != "prohibited":
        return req
    updated = req.model_copy(deep=True)
    updated.assumptions = [
        text
        for text in updated.assumptions
        if not (AI_TERMS.search(text) and not LOCAL_MARKERS.search(text))
    ]
    updated.integrations = [
        item
        for item in updated.integrations
        if not EXTERNAL_AI_TERMS.search(" ".join([item.name, item.purpose, item.protocol]))
    ]
    for name, value in updated.architecture.model_dump().items():
        if value and EXTERNAL_AI_TERMS.search(value):
            setattr(updated.architecture, name, "")
        elif value:
            setattr(updated.architecture, name, _localize_ai_text(value))
    for item in updated.functional_requirements:
        item.title = _localize_ai_text(item.title)
        item.description = _localize_ai_text(item.description)
        item.acceptance_criteria = [_localize_ai_text(value) for value in item.acceptance_criteria]
    for item in updated.non_functional_requirements:
        item.requirement = _localize_ai_text(item.requirement)
        item.target = _localize_ai_text(item.target)
    return updated


def apply_paid_ai_choice(req: Requirements, choice: PaidAIChoice) -> Requirements:
    if choice not in {"prohibited", "allowed"}:
        return req
    updated = req.model_copy(deep=True)
    decision_text = "使用しない" if choice == "prohibited" else "利用を許可する"
    existing = next((item for item in updated.decisions if item.topic == PAID_AI_TOPIC), None)
    if existing:
        existing.decision = decision_text
        existing.status = "confirmed"
        existing.rationale = "利用者が画面上で明示的に選択"
    else:
        updated.decisions.append(
            Decision(
                id=_next_decision_id(updated),
                topic=PAID_AI_TOPIC,
                decision=decision_text,
                rationale="利用者が画面上で明示的に選択",
                status="confirmed",
            )
        )
    if choice == "prohibited":
        constraint = "実行時にClaude、OpenAI等の有料AI APIを使用しない。"
        if constraint not in updated.constraints:
            updated.constraints.append(constraint)
    updated.revision += 1
    return enforce_paid_ai_prohibition(updated)


def design_policy_warnings(req: Requirements) -> list[DesignWarning]:
    """目的と実行時AI依存の矛盾を、LLMを使わず決定的に検出する。"""
    if not (minimizes_external_ai(req) or _runtime_ai_statements(req)):
        return []

    choice = paid_ai_choice(req)
    if choice == "unknown":
        return [
            DesignWarning(
                code="PAID_AI_CONFIRMATION_REQUIRED",
                severity="blocking",
                title="有料AIを使うか決めてください",
                detail=(
                    "画像判定などにAIを使う案がありますが、Claudeなどの有料AIを"
                    "使うか、まだ確認できていません。"
                ),
                recommendation=(
                    "使わない場合は、ルール、OSS、ローカルモデル、人による確認だけで設計します。"
                ),
            )
        ]
    if choice == "allowed":
        return []

    statements = _runtime_ai_statements(req)
    explicit_external = [text for text in statements if EXTERNAL_AI_TERMS.search(text)]
    unspecified = [
        text
        for text in statements
        if not EXTERNAL_AI_TERMS.search(text) and not LOCAL_MARKERS.search(text)
    ]
    warnings: list[DesignWarning] = []
    if explicit_external:
        warnings.append(
            DesignWarning(
                code="EXTERNAL_AI_CONFLICT",
                severity="blocking",
                title="外部AI依存がプロジェクト目的と矛盾しています",
                detail=f"実行時の外部AI利用案: {explicit_external[0][:180]}",
                recommendation=(
                    "通常プログラム、ルール判定、OSS、ローカルモデルの順に置き換え、"
                    "外部AIを使う場合は対象処理・理由・月間上限費用を明記してください。"
                ),
            )
        )
    if unspecified:
        warnings.append(
            DesignWarning(
                code="AI_RUNTIME_UNSPECIFIED",
                severity="warning",
                title="AIの実行場所と費用が未定義です",
                detail=f"実行方式が曖昧なAI利用案: {unspecified[0][:180]}",
                recommendation=(
                    "ローカルVLM/Ollama等の実行方式を明記し、ルール処理で代替できない"
                    "範囲だけにAI利用を限定してください。"
                ),
            )
        )
    return warnings


def design_policy_context(req: Requirements) -> str:
    """Gemmaへ渡す、コード判定済みの設計制約。"""
    if not (minimizes_external_ai(req) or _runtime_ai_statements(req)):
        return "コード判定による追加制約はありません。"

    choice = paid_ai_choice(req)
    if choice == "unknown":
        return f"""
コードが検出した必須確認事項:
- {PAID_AI_QUESTION}
- 利用者が回答するまで、AIを使う構成を提案・確定してはいけない。
- この確認以外の新しい質問をしてはいけない。
""".strip()
    if choice == "allowed":
        return "有料AIの利用は許可されています。利用箇所、呼出頻度、月間費用上限を明記してください。"

    warnings = design_policy_warnings(req)
    detected = "\n".join(f"- {item.title}: {item.detail}" for item in warnings)
    return f"""
コードが検出した最優先目的: 外部LLMのトークン消費・費用を削減すること。
必須ルール:
- Claude、OpenAI等の有料AIは実行時に使用しない。
- 通常プログラム、決定的ルール、OSS、ローカルモデルの順に検討する。
- AIが不可欠な処理は、実行場所、モデル、呼出頻度、費用上限、非AI代替案を明記する。
- 画像理解が必要なら、まずローカルVLMまたは専用画像認識モデルを検討する。

現在の矛盾・未定義:
{detected or '- なし'}
""".strip()
