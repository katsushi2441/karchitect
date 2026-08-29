from app.models import FunctionalRequirement, Integration, Requirements
from app.policies import design_policy_context, design_policy_warnings, minimizes_external_ai


def _cost_reduction_project(**changes) -> Requirements:
    values = {
        "purpose": "Claudeへの直接入力によるトークン消費を削減する。",
        "background": "現在の高コストな運用をシステム化したい。",
    }
    values.update(changes)
    return Requirements(**values)


def test_detects_unspecified_runtime_llm_conflict():
    req = _cost_reduction_project(
        assumptions=["SV解析はLLMによる一次判断を行う。"],
    )

    warnings = design_policy_warnings(req)

    assert minimizes_external_ai(req)
    assert [item.code for item in warnings] == ["AI_RUNTIME_UNSPECIFIED"]
    assert "ローカルVLM" in warnings[0].recommendation


def test_detects_explicit_external_ai_conflict():
    req = _cost_reduction_project(
        integrations=[Integration(name="OpenAI API", purpose="画像解析")],
    )

    warnings = design_policy_warnings(req)

    assert warnings[0].code == "EXTERNAL_AI_CONFLICT"
    assert warnings[0].severity == "blocking"


def test_local_model_is_not_reported_as_conflict():
    req = _cost_reduction_project(
        functional_requirements=[
            FunctionalRequirement(
                id="FR-1",
                title="画像解析",
                description="ローカルVLMで画像を解析する。",
            )
        ],
    )

    assert design_policy_warnings(req) == []


def test_projects_without_cost_reduction_goal_are_not_restricted():
    req = Requirements(
        purpose="高品質な回答を提供する。",
        integrations=[Integration(name="OpenAI API", purpose="回答生成")],
    )

    assert not minimizes_external_ai(req)
    assert design_policy_warnings(req) == []


def test_policy_context_tells_llm_not_to_default_to_external_ai():
    context = design_policy_context(_cost_reduction_project())

    assert "外部LLMを実行時の既定構成として提案・確定しない" in context
    assert "通常プログラム" in context
