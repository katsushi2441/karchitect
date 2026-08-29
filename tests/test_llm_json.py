import json

import pytest

from app.llm import OllamaError, _parse_json_content


def test_parse_json_content_accepts_valid_json():
    value = {"assistant_message": "ok", "requirements": {"project_name": "test"}}
    assert _parse_json_content(json.dumps(value)) == value


def test_parse_json_content_recovers_truncated_tail():
    value = {
        "assistant_message": "ok",
        "requirements": {"project_name": "test", "raw_notes": ["saved"]},
        "next_questions": ["question"],
    }
    content = json.dumps(value, ensure_ascii=False)
    truncated = content[:-5]

    result = _parse_json_content(truncated)

    assert result["assistant_message"] == "ok"
    assert result["requirements"]["raw_notes"] == ["saved"]


def test_parse_json_content_rejects_early_corruption():
    content = '{"assistant_message": invalid, "requirements": {"project_name": "test"}}'
    with pytest.raises(OllamaError, match="解析できません"):
        _parse_json_content(content)
