from app.models import FunctionalRequirement, Integration, Requirements
from app.policies import (
    apply_paid_ai_choice,
    design_policy_context,
    design_policy_warnings,
    enforce_paid_ai_prohibition,
    minimizes_external_ai,
    paid_ai_choice,
    paid_ai_policy_question,
    parse_paid_ai_answer,
)


def _cost_reduction_project(**changes) -> Requirements:
    values = {
        "purpose": "Claudeへの直接入力によるトークン消費を削減する。",
        "background": "現在の高コストな運用をシステム化したい。",
    }
    values.update(changes)
    return Requirements(**values)


def test_requires_paid_ai_confirmation_before_designing_runtime_ai():
    req = _cost_reduction_project(
        assumptions=["SV解析はLLMによる一次判断を行う。"],
    )

    warnings = design_policy_warnings(req)

    assert minimizes_external_ai(req)
    assert [item.code for item in warnings] == ["PAID_AI_CONFIRMATION_REQUIRED"]
    assert warnings[0].severity == "blocking"
    assert paid_ai_policy_question(req) is not None


def test_explicit_external_ai_still_requires_confirmation_first():
    req = _cost_reduction_project(
        integrations=[Integration(name="OpenAI API", purpose="画像解析")],
    )

    warnings = design_policy_warnings(req)

    assert warnings[0].code == "PAID_AI_CONFIRMATION_REQUIRED"
    assert warnings[0].severity == "blocking"


def test_local_model_project_still_asks_the_paid_ai_question():
    req = _cost_reduction_project(
        functional_requirements=[
            FunctionalRequirement(
                id="FR-1",
                title="画像解析",
                description="ローカルVLMで画像を解析する。",
            )
        ],
    )

    assert design_policy_warnings(req)[0].code == "PAID_AI_CONFIRMATION_REQUIRED"


def test_any_project_with_paid_ai_dependency_requires_confirmation():
    req = Requirements(
        purpose="高品質な回答を提供する。",
        integrations=[Integration(name="OpenAI API", purpose="回答生成")],
    )

    assert not minimizes_external_ai(req)
    assert design_policy_warnings(req)[0].code == "PAID_AI_CONFIRMATION_REQUIRED"


def test_policy_context_tells_llm_not_to_default_to_external_ai():
    context = design_policy_context(_cost_reduction_project())

    assert "有料AIを使いますか" in context
    assert "回答するまで、AIを使う構成を提案・確定してはいけない" in context


def test_prohibited_choice_is_applied_without_llm_and_removes_old_assumption():
    req = _cost_reduction_project(
        assumptions=["SV解析はLLMによる一次判断を行う。"],
    )

    updated = apply_paid_ai_choice(req, "prohibited")

    assert paid_ai_choice(updated) == "prohibited"
    assert updated.assumptions == []
    assert any("有料AI APIを使用しない" in item for item in updated.constraints)
    assert any(item.topic == "実行時の有料AI利用" for item in updated.decisions)
    assert paid_ai_policy_question(updated) is None
    assert design_policy_warnings(updated) == []


def test_allowed_choice_permits_external_ai():
    req = _cost_reduction_project(
        integrations=[Integration(name="OpenAI API", purpose="画像解析")],
    )

    updated = apply_paid_ai_choice(req, "allowed")

    assert paid_ai_choice(updated) == "allowed"
    assert design_policy_warnings(updated) == []


def test_prohibited_policy_removes_external_integration():
    req = apply_paid_ai_choice(_cost_reduction_project(), "prohibited")
    req.integrations = [Integration(name="OpenAI API", purpose="画像解析")]

    enforced = enforce_paid_ai_prohibition(req)

    assert enforced.integrations == []


def test_prohibited_policy_localizes_llm_in_functional_requirement():
    req = _cost_reduction_project(
        functional_requirements=[
            FunctionalRequirement(
                id="FR-1",
                title="AI解析",
                description="LLMにより人通りのスコアを算出する。",
                acceptance_criteria=["Claudeで画像を判定できる。"],
            )
        ]
    )

    updated = apply_paid_ai_choice(req, "prohibited")
    requirement = updated.functional_requirements[0]

    assert requirement.title == "ローカル画像解析"
    assert "ローカルモデル" in requirement.description
    assert "Claude" not in requirement.acceptance_criteria[0]
    assert design_policy_warnings(updated) == []


def test_natural_button_answers_are_recognized():
    assert parse_paid_ai_answer("有料AIは使いません") == "prohibited"
    assert parse_paid_ai_answer("有料AIの利用を許可します") == "allowed"
