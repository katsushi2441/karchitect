from app.documents import build_markdown
from app.engine import completeness, fallback_turn
from app.models import (
    DataEntity,
    FunctionalRequirement,
    NonFunctionalRequirement,
    OpenQuestion,
    Requirements,
    Risk,
)


def test_completeness_tracks_design_coverage() -> None:
    empty = Requirements(project_name="Test")
    assert completeness(empty) == 0
    filled = Requirements(
        project_name="Test",
        purpose="予約を簡単にする",
        target_users=["顧客"],
        in_scope=["予約"],
        functional_requirements=[
            FunctionalRequirement(
                id="FR-001",
                title="予約登録",
                acceptance_criteria=["日時を指定して保存できる"],
            )
        ],
        non_functional_requirements=[
            NonFunctionalRequirement(category="性能", requirement="応答時間", target="2秒以内")
        ],
        data_entities=[DataEntity(name="Reservation")],
        risks=[Risk(title="二重予約")],
        stage="ready",
    )
    filled.architecture.backend = "FastAPI"
    assert completeness(filled) == 100


def test_fallback_never_loses_user_message() -> None:
    requirements = Requirements(project_name="Test")
    result = fallback_turn(requirements, "店舗予約を作りたい", "offline")
    assert "店舗予約を作りたい" in result.requirements.raw_notes
    assert result.next_questions
    assert result.requirements.revision == 2


def test_document_contains_mermaid_and_open_questions() -> None:
    requirements = Requirements(
        project_name="予約システム",
        summary="店舗予約を管理する",
        open_questions=[
            OpenQuestion(id="Q001", question="決済は必要ですか？", importance="blocking")
        ],
    )
    document = build_markdown(requirements)
    assert "# 予約システム システム設計書" in document
    assert document.count("```mermaid") == 3
    assert "決済は必要ですか？" in document
