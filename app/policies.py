from __future__ import annotations

import re

from .models import DesignWarning, Requirements


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
    return [text.strip() for text in statements if text and AI_TERMS.search(text)]


def design_policy_warnings(req: Requirements) -> list[DesignWarning]:
    """目的と実行時AI依存の矛盾を、LLMを使わず決定的に検出する。"""
    if not minimizes_external_ai(req):
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
    if not minimizes_external_ai(req):
        return "コード判定による追加制約はありません。"

    warnings = design_policy_warnings(req)
    detected = "\n".join(f"- {item.title}: {item.detail}" for item in warnings)
    return f"""
コードが検出した最優先目的: 外部LLMのトークン消費・費用を削減すること。
必須ルール:
- Claude、OpenAI等の外部LLMを実行時の既定構成として提案・確定しない。
- 通常プログラム、決定的ルール、OSS、ローカルモデルの順に検討する。
- AIが不可欠な処理は、実行場所、モデル、呼出頻度、費用上限、非AI代替案を明記する。
- 画像理解が必要なら、まずローカルVLMまたは専用画像認識モデルを検討する。

現在の矛盾・未定義:
{detected or '- なし'}
""".strip()
