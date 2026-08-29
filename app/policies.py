from __future__ import annotations

import re
from typing import Literal

from .models import Decision, DesignWarning, PolicyOption, PolicyQuestion, Requirements


PolicyChoice = Literal["unknown", "prohibited", "allowed"]
RUNTIME_AI_TOPIC = "実行時のAI利用"
PAID_API_TOPIC = "有料外部API利用"
RUNTIME_AI_QUESTION = "このシステムの運用時に、AI・LLM・VLMを使いますか？"
PAID_API_QUESTION = "このシステムの運用時に、利用料が発生する可能性のある外部APIを使いますか？"

AI_TERMS = re.compile(
    r"(?:LLM|VLM|Claude|ChatGPT|OpenAI|Gemini|GPT|生成AI|AI解析|AI判定|"
    r"ローカルモデル|画像認識モデル|機械学習|ディープラーニング|"
    r"(?<![A-Za-z])AI(?![A-Za-z]))",
    re.IGNORECASE,
)
EXTERNAL_API_TERMS = re.compile(
    r"(?:Google\s+(?:Street\s+View|Maps)\s+API|外部API|"
    r"(?<![A-Za-z])API(?:$|[\s、。)]|連携|を|で|経由|利用|使用))",
    re.IGNORECASE,
)
FREE_API_MARKERS = re.compile(r"(?:無料|無償|自社|内部|セルフホスト|self-hosted)", re.IGNORECASE)
REDUCTION_TERMS = re.compile(
    r"(?:抑え|削減|減ら|節約|回避|依存しない|使わない|高コスト|大量に消費)",
    re.IGNORECASE,
)
RUNTIME_AI_NO_ANSWER = re.compile(
    r"(?:実行時AI|AI・LLM・VLM|AI|LLM|VLM).*(?:使わない|使いません|使用しない|禁止)",
    re.IGNORECASE,
)
RUNTIME_AI_YES_ANSWER = re.compile(
    r"(?:実行時AI|AI・LLM・VLM|AI|LLM|VLM).*(?:使います|使用する|利用を許可|利用可)",
    re.IGNORECASE,
)
PAID_API_NO_ANSWER = re.compile(
    r"(?:有料外部API|有料API|利用料.*外部API).*(?:使わない|使いません|使用しない|禁止)",
    re.IGNORECASE,
)
PAID_API_YES_ANSWER = re.compile(
    r"(?:有料外部API|有料API|利用料.*外部API).*(?:使います|使用する|利用を許可|利用可)",
    re.IGNORECASE,
)


def _goal_text(req: Requirements) -> str:
    return "\n".join([req.summary, req.purpose, req.background, *req.raw_notes])


def minimizes_external_ai(req: Requirements) -> bool:
    text = _goal_text(req)
    has_ai_cost_subject = bool(
        re.search(r"(?:トークン|Claude|ChatGPT|OpenAI|LLM.*(?:費用|コスト))", text, re.I)
    )
    return has_ai_cost_subject and bool(REDUCTION_TERMS.search(text))


def _is_runtime_ai_prohibition(text: str) -> bool:
    return "実行時にAI、LLM、VLM、ローカルモデルを使用しない" in text


def _is_paid_api_prohibition(text: str) -> bool:
    return "利用料が発生する外部APIを使用しない" in text


def _runtime_ai_statements(req: Requirements) -> list[str]:
    statements = [
        *req.assumptions,
        *[item for item in req.constraints if not _is_runtime_ai_prohibition(item)],
    ]
    for item in req.functional_requirements:
        statements.extend([item.title, item.description, *item.acceptance_criteria])
    for item in req.non_functional_requirements:
        statements.extend([item.requirement, item.target])
    for item in req.integrations:
        statements.extend([item.name, item.purpose, item.protocol])
    statements.extend(req.architecture.model_dump().values())
    return [text.strip() for text in statements if text and AI_TERMS.search(text)]


def _external_api_statements(req: Requirements) -> list[str]:
    statements = [
        *req.assumptions,
        *[item for item in req.constraints if not _is_paid_api_prohibition(item)],
    ]
    for item in req.functional_requirements:
        statements.extend([item.title, item.description, *item.acceptance_criteria])
    for item in req.integrations:
        statements.extend([item.name, item.purpose, item.protocol])
    return [
        text.strip()
        for text in statements
        if text and EXTERNAL_API_TERMS.search(text) and not FREE_API_MARKERS.search(text)
    ]


def _decision_choice(req: Requirements, topic: str) -> PolicyChoice:
    for item in reversed(req.decisions):
        if item.topic != topic or item.status != "confirmed":
            continue
        if re.search(r"(?:使用しない|使わない|禁止)", item.decision):
            return "prohibited"
        if re.search(r"(?:使用する|利用を許可|利用可)", item.decision):
            return "allowed"
    return "unknown"


def runtime_ai_choice(req: Requirements) -> PolicyChoice:
    choice = _decision_choice(req, RUNTIME_AI_TOPIC)
    if choice != "unknown":
        return choice
    return "prohibited" if any(_is_runtime_ai_prohibition(item) for item in req.constraints) else "unknown"


def paid_api_choice(req: Requirements) -> PolicyChoice:
    choice = _decision_choice(req, PAID_API_TOPIC)
    if choice != "unknown":
        return choice
    return "prohibited" if any(_is_paid_api_prohibition(item) for item in req.constraints) else "unknown"


def next_policy_question(req: Requirements) -> PolicyQuestion | None:
    ai_relevant = (
        minimizes_external_ai(req)
        or bool(AI_TERMS.search(_goal_text(req)))
        or bool(_runtime_ai_statements(req))
    )
    if ai_relevant and runtime_ai_choice(req) == "unknown":
        return PolicyQuestion(
            code="RUNTIME_AI_USAGE",
            question=RUNTIME_AI_QUESTION,
            options=[
                PolicyOption(
                    label="使わない",
                    value="実行時AIは使いません",
                    description="固定ルール、通常処理、担当者確認だけで設計します。",
                ),
                PolicyOption(
                    label="利用を許可",
                    value="実行時AIの利用を許可します",
                    description="利用箇所と実行方式を設計します。",
                ),
            ],
        )
    if _external_api_statements(req) and paid_api_choice(req) == "unknown":
        return PolicyQuestion(
            code="PAID_EXTERNAL_API_USAGE",
            question=PAID_API_QUESTION,
            options=[
                PolicyOption(
                    label="使わない",
                    value="有料外部APIは使いません",
                    description="公開データ取込または担当者入力で設計します。",
                ),
                PolicyOption(
                    label="利用を許可",
                    value="有料外部APIの利用を許可します",
                    description="利用箇所と月間費用上限を設計します。",
                ),
            ],
        )
    return None


def parse_policy_answer(content: str, code: str) -> PolicyChoice:
    if code == "RUNTIME_AI_USAGE":
        if RUNTIME_AI_NO_ANSWER.search(content):
            return "prohibited"
        if RUNTIME_AI_YES_ANSWER.search(content):
            return "allowed"
    if code == "PAID_EXTERNAL_API_USAGE":
        if PAID_API_NO_ANSWER.search(content):
            return "prohibited"
        if PAID_API_YES_ANSWER.search(content):
            return "allowed"
    return "unknown"


def _next_decision_id(req: Requirements) -> str:
    used = {item.id for item in req.decisions}
    number = len(used) + 1
    while f"D{number:03d}" in used:
        number += 1
    return f"D{number:03d}"


def _save_decision(req: Requirements, topic: str, choice: PolicyChoice) -> None:
    decision_text = "使用しない" if choice == "prohibited" else "利用を許可する"
    existing = next((item for item in req.decisions if item.topic == topic), None)
    if existing:
        existing.decision = decision_text
        existing.status = "confirmed"
        existing.rationale = "利用者が画面上で明示的に選択"
        return
    req.decisions.append(
        Decision(
            id=_next_decision_id(req),
            topic=topic,
            decision=decision_text,
            rationale="利用者が画面上で明示的に選択",
            status="confirmed",
        )
    )


def _without_ai_sentences(text: str, replacement: str) -> str:
    if not text or not AI_TERMS.search(text):
        return text
    parts = re.split(r"(?<=[。！？])", text)
    result: list[str] = []
    inserted = False
    for part in parts:
        if AI_TERMS.search(part):
            if not inserted:
                result.append(replacement)
                inserted = True
        else:
            result.append(part)
    return "".join(result).strip()


def enforce_runtime_ai_prohibition(req: Requirements) -> Requirements:
    if runtime_ai_choice(req) != "prohibited":
        return req
    updated = req.model_copy(deep=True)
    updated.assumptions = [text for text in updated.assumptions if not AI_TERMS.search(text)]
    updated.integrations = [
        item
        for item in updated.integrations
        if not AI_TERMS.search(" ".join([item.name, item.purpose, item.protocol]))
    ]
    for name, value in updated.architecture.model_dump().items():
        if value and AI_TERMS.search(value):
            setattr(updated.architecture, name, "")

    description = "取得可能な数値データと固定ルールで処理し、画像判断が必要な項目は担当者が確認する。"
    criterion = "固定ルールで判定できない場合は、担当者確認として明示される。"
    for item in updated.functional_requirements:
        if AI_TERMS.search(item.title):
            item.title = "ルール判定・担当者確認"
        item.description = _without_ai_sentences(item.description, description)
        item.acceptance_criteria = [
            _without_ai_sentences(value, criterion) for value in item.acceptance_criteria
        ]
    for item in updated.non_functional_requirements:
        item.requirement = _without_ai_sentences(item.requirement, "通常プログラムだけで要件を満たす。")
        item.target = _without_ai_sentences(item.target, "担当者が確認可能な時間内に処理する。")
    return updated


def _without_paid_api_sentences(text: str) -> str:
    if not text or not EXTERNAL_API_TERMS.search(text) or FREE_API_MARKERS.search(text):
        return text
    replacement = "外部の有料APIを使わず、公開データの取込または担当者入力で処理する。"
    parts = re.split(r"(?<=[。！？])", text)
    result: list[str] = []
    inserted = False
    for part in parts:
        if EXTERNAL_API_TERMS.search(part) and not FREE_API_MARKERS.search(part):
            if not inserted:
                result.append(replacement)
                inserted = True
        else:
            result.append(part)
    return "".join(result).strip()


def enforce_paid_api_prohibition(req: Requirements) -> Requirements:
    if paid_api_choice(req) != "prohibited":
        return req
    updated = req.model_copy(deep=True)
    updated.assumptions = [
        text
        for text in updated.assumptions
        if not (EXTERNAL_API_TERMS.search(text) and not FREE_API_MARKERS.search(text))
    ]
    updated.integrations = [
        item
        for item in updated.integrations
        if not (
            EXTERNAL_API_TERMS.search(" ".join([item.name, item.purpose, item.protocol]))
            and not FREE_API_MARKERS.search(" ".join([item.name, item.purpose, item.protocol]))
        )
    ]
    for item in updated.functional_requirements:
        item.title = _without_paid_api_sentences(item.title)
        item.description = _without_paid_api_sentences(item.description)
        item.acceptance_criteria = [_without_paid_api_sentences(value) for value in item.acceptance_criteria]
    return updated


def enforce_design_policies(req: Requirements) -> Requirements:
    return enforce_paid_api_prohibition(enforce_runtime_ai_prohibition(req))


def apply_policy_choice(req: Requirements, code: str, choice: PolicyChoice) -> Requirements:
    if choice not in {"prohibited", "allowed"}:
        return req
    updated = req.model_copy(deep=True)
    if code == "RUNTIME_AI_USAGE":
        _save_decision(updated, RUNTIME_AI_TOPIC, choice)
        if choice == "prohibited":
            constraint = "実行時にAI、LLM、VLM、ローカルモデルを使用しない。"
            if constraint not in updated.constraints:
                updated.constraints.append(constraint)
    elif code == "PAID_EXTERNAL_API_USAGE":
        _save_decision(updated, PAID_API_TOPIC, choice)
        if choice == "prohibited":
            constraint = "利用料が発生する外部APIを使用しない。"
            if constraint not in updated.constraints:
                updated.constraints.append(constraint)
    else:
        return req
    updated.revision += 1
    return enforce_design_policies(updated)


def design_policy_warnings(req: Requirements) -> list[DesignWarning]:
    question = next_policy_question(req)
    if question:
        if question.code == "RUNTIME_AI_USAGE":
            return [
                DesignWarning(
                    code="RUNTIME_AI_CONFIRMATION_REQUIRED",
                    severity="blocking",
                    title="実行時にAIを使うか決めてください",
                    detail="ローカルモデルを含め、運用時にAIを使うかまだ確認できていません。",
                    recommendation="使わない場合は、固定ルール、通常処理、担当者確認だけで設計します。",
                )
            ]
        return [
            DesignWarning(
                code="PAID_API_CONFIRMATION_REQUIRED",
                severity="blocking",
                title="有料の外部APIを使うか決めてください",
                detail="利用料が発生する可能性のある外部APIを使うか確認できていません。",
                recommendation="使わない場合は、公開データ取込または担当者入力で設計します。",
            )
        ]

    warnings: list[DesignWarning] = []
    ai_statements = _runtime_ai_statements(req)
    if runtime_ai_choice(req) == "prohibited" and ai_statements:
        warnings.append(
            DesignWarning(
                code="RUNTIME_AI_CONFLICT",
                severity="blocking",
                title="AIを使わない方針と設計内容が矛盾しています",
                detail=f"AI利用案が残っています: {ai_statements[0][:180]}",
                recommendation="固定ルール、通常処理、担当者確認へ変更してください。",
            )
        )
    api_statements = _external_api_statements(req)
    if paid_api_choice(req) == "prohibited" and api_statements:
        warnings.append(
            DesignWarning(
                code="PAID_API_CONFLICT",
                severity="blocking",
                title="有料APIを使わない方針と設計内容が矛盾しています",
                detail=f"外部API利用案が残っています: {api_statements[0][:180]}",
                recommendation="公開データ取込または担当者入力へ変更してください。",
            )
        )
    return warnings


def design_policy_context(req: Requirements) -> str:
    question = next_policy_question(req)
    if question:
        return f"""
コードが検出した必須確認事項:
- {question.question}
- 利用者が回答するまで、この方針に関係する構成を提案・確定してはいけない。
- この確認以外の新しい質問をしてはいけない。
""".strip()

    rules: list[str] = []
    if runtime_ai_choice(req) == "prohibited":
        rules.append("実行時にAI・LLM・VLM・ローカルモデルを使用しない。固定ルールと担当者確認で設計する。")
    elif runtime_ai_choice(req) == "allowed":
        rules.append("実行時AIの利用は許可されている。利用箇所と実行方式を明記する。")
    if paid_api_choice(req) == "prohibited":
        rules.append("利用料が発生する外部APIを使用しない。公開データ取込または担当者入力で設計する。")
    elif paid_api_choice(req) == "allowed":
        rules.append("有料外部APIの利用は許可されている。利用箇所と月間費用上限を明記する。")
    return "\n".join(f"- {item}" for item in rules) or "コード判定による追加制約はありません。"
