import json

import pytest

from app.llm import OllamaError, _build_output, _parse_json_content
from app.models import Requirements


def test_parse_json_content_accepts_valid_json():
    value = {"assistant_message": "ok", "patch": {"project_name": "test"}}
    assert _parse_json_content(json.dumps(value)) == value


def test_parse_json_content_recovers_truncated_tail():
    value = {
        "assistant_message": "ok",
        "patch": {"project_name": "test", "raw_notes_append": ["saved"]},
        "next_questions": ["question"],
    }
    content = json.dumps(value, ensure_ascii=False)
    truncated = content[:-5]

    result = _parse_json_content(truncated)

    assert result["assistant_message"] == "ok"
    assert result["patch"]["raw_notes_append"] == ["saved"]


def test_parse_json_content_rejects_early_corruption():
    content = '{"assistant_message": invalid, "patch": {"project_name": "test"}}'
    with pytest.raises(OllamaError, match="解析できません"):
        _parse_json_content(content)


def test_build_output_merges_delta_without_repeating_requirements():
    previous = Requirements(project_name="既存", purpose="残す目的", raw_notes=["既存メモ"], revision=7)
    content = json.dumps(
        {
            "assistant_message": "対象利用者を追加しました。",
            "patch": {"target_users": ["管理者"], "raw_notes_append": ["新しいメモ"]},
            "next_questions": [],
            "changed_summary": ["対象利用者を追加"],
        },
        ensure_ascii=False,
    )

    result = _build_output(content, previous)

    assert result.assistant_message == "対象利用者を追加しました。"
    assert result.requirements.project_name == "既存"
    assert result.requirements.purpose == "残す目的"
    assert result.requirements.target_users == ["管理者"]
    assert result.requirements.raw_notes == ["既存メモ", "新しいメモ"]
    assert result.requirements.revision == 8
