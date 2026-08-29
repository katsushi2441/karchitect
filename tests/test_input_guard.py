from app.input_guard import (
    append_raw_note,
    classify_user_input,
    completion_body,
    is_completion,
    is_continuation,
)
from app.models import Message, Requirements


def _message(role: str, content: str, message_id: int = 1) -> Message:
    return Message(id=message_id, role=role, content=content, created_at="2026-08-29T00:00:00+09:00")


def test_continuation_is_saved_without_llm():
    decision = classify_user_input("まだ続く。③ 視認性", Requirements(), [])
    assert is_continuation("まだ続く。③ 視認性")
    assert decision.action == "save_only"
    assert "AI解析は実行していません" in decision.response


def test_completion_runs_llm_and_keeps_body():
    content = "最後の条件です。\n入力完了"
    decision = classify_user_input(content, Requirements(), [])
    assert is_completion(content)
    assert decision.action == "llm"
    assert completion_body(content) == "最後の条件です。"


def test_yes_is_rejected_for_open_question():
    messages = [_message("assistant", "主な利用者は誰ですか？")]
    decision = classify_user_input("はい", Requirements(), messages)
    assert decision.action == "reject"
    assert "AI解析は実行していません" in decision.response
    assert "主な利用者" in decision.response


def test_yes_is_allowed_for_confirmation_question():
    messages = [_message("assistant", "この構成で進めてよろしいですか？")]
    assert classify_user_input("はい", Requirements(), messages).action == "llm"


def test_no_is_allowed_for_existence_question():
    messages = [_message("assistant", "期限の制約はありますか？")]
    assert classify_user_input("ありません", Requirements(), messages).action == "llm"


def test_duplicate_skips_llm():
    messages = [_message("user", "対象は営業担当者です")]
    decision = classify_user_input("対象は営業担当者です", Requirements(), messages)
    assert decision.action == "duplicate"


def test_raw_note_is_appended_without_mutating_original():
    original = Requirements(raw_notes=["既存"], revision=4)
    updated = append_raw_note(original, "続き")
    assert original.raw_notes == ["既存"]
    assert updated.raw_notes == ["既存", "続き"]
    assert updated.revision == 5
