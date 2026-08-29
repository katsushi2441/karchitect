from app.models import FunctionalRequirement, Integration, Requirements
from app.policies import (
    apply_policy_choice,
    design_policy_context,
    design_policy_warnings,
    enforce_design_policies,
    next_policy_question,
    paid_api_choice,
    parse_policy_answer,
    runtime_ai_choice,
)


def _ai_project(**changes) -> Requirements:
    values = {
        "purpose": "Claudeへの直接入力によるトークン消費を削減する。",
        "background": "現在の高コストな運用をシステム化したい。",
    }
    values.update(changes)
    return Requirements(**values)


def test_runtime_ai_is_confirmed_before_architecture_design():
    req = _ai_project(assumptions=["SV解析はLLMによる一次判断を行う。"])

    question = next_policy_question(req)
    warnings = design_policy_warnings(req)

    assert question is not None
    assert question.code == "RUNTIME_AI_USAGE"
    assert "AI・LLM・VLM" in question.question
    assert warnings[0].code == "RUNTIME_AI_CONFIRMATION_REQUIRED"
    assert "ローカルモデルを含め" in warnings[0].detail


def test_local_model_is_treated_as_runtime_ai():
    req = Requirements(
        purpose="画像を判定する。",
        functional_requirements=[
            FunctionalRequirement(
                id="FR-1",
                title="画像解析",
                description="ローカルモデルで画像を判定する。",
            )
        ],
    )

    assert next_policy_question(req).code == "RUNTIME_AI_USAGE"


def test_generic_ai_word_is_treated_as_runtime_ai():
    req = Requirements(purpose="AIで書類を確認するシステム")

    assert next_policy_question(req).code == "RUNTIME_AI_USAGE"


def test_external_api_is_confirmed_separately_from_ai():
    req = Requirements(
        purpose="地図情報を表示する。",
        integrations=[Integration(name="Google Maps API", purpose="地図取得")],
    )

    question = next_policy_question(req)

    assert question.code == "PAID_EXTERNAL_API_USAGE"
    assert "利用料" in question.question


def test_disabling_runtime_ai_removes_local_and_external_models():
    req = _ai_project(
        assumptions=["SV解析はLLMによる一次判断を行う。"],
        functional_requirements=[
            FunctionalRequirement(
                id="FR-1",
                title="AI解析",
                description="ローカルモデルで画像を判定する。",
                acceptance_criteria=["Claudeで画像を判定できる。"],
            )
        ],
    )

    updated = apply_policy_choice(req, "RUNTIME_AI_USAGE", "prohibited")
    requirement = updated.functional_requirements[0]

    assert runtime_ai_choice(updated) == "prohibited"
    assert updated.assumptions == []
    assert requirement.title == "ルール判定・担当者確認"
    assert "ローカルモデル" not in requirement.description
    assert "Claude" not in requirement.acceptance_criteria[0]
    assert any("ローカルモデルを使用しない" in item for item in updated.constraints)
    assert design_policy_warnings(updated) == []


def test_paid_api_question_follows_when_ai_choice_is_done():
    req = _ai_project(
        integrations=[Integration(name="Google Street View API", purpose="画像取得")],
    )

    updated = apply_policy_choice(req, "RUNTIME_AI_USAGE", "allowed")

    assert runtime_ai_choice(updated) == "allowed"
    assert next_policy_question(updated).code == "PAID_EXTERNAL_API_USAGE"


def test_disabling_paid_api_removes_external_api_dependency():
    req = Requirements(
        purpose="地図情報を表示する。",
        integrations=[Integration(name="Google Maps API", purpose="地図取得")],
    )

    updated = apply_policy_choice(req, "PAID_EXTERNAL_API_USAGE", "prohibited")

    assert paid_api_choice(updated) == "prohibited"
    assert updated.integrations == []
    assert any("利用料が発生する外部APIを使用しない" in item for item in updated.constraints)
    assert next_policy_question(updated) is None


def test_runtime_ai_prohibition_is_reapplied_after_llm_output():
    req = apply_policy_choice(_ai_project(), "RUNTIME_AI_USAGE", "prohibited")
    req.assumptions = ["ローカルVLMで一次判定する。"]

    enforced = enforce_design_policies(req)

    assert enforced.assumptions == []


def test_policy_answers_are_specific_to_each_question():
    assert parse_policy_answer("実行時AIは使いません", "RUNTIME_AI_USAGE") == "prohibited"
    assert parse_policy_answer("実行時AIの利用を許可します", "RUNTIME_AI_USAGE") == "allowed"
    assert parse_policy_answer("有料外部APIは使いません", "PAID_EXTERNAL_API_USAGE") == "prohibited"
    assert parse_policy_answer("有料外部APIの利用を許可します", "PAID_EXTERNAL_API_USAGE") == "allowed"
    assert parse_policy_answer("有料外部APIは使いません", "RUNTIME_AI_USAGE") == "unknown"


def test_policy_context_forbids_local_models_when_ai_is_disabled():
    req = apply_policy_choice(_ai_project(), "RUNTIME_AI_USAGE", "prohibited")
    context = design_policy_context(req)

    assert "ローカルモデルを使用しない" in context
    assert "固定ルールと担当者確認" in context
