from app.response_quality import normalize_assistant_message, response_quality_issues


def test_detects_dangling_following_reference():
    message = "以下について確認してください。"
    assert "dangling_reference" in response_quality_issues(message)


def test_detects_missing_declared_items():
    message = "以下の3点を確認します。\n1. 利用者は誰ですか？"
    assert "missing_list_items" in response_quality_issues(message)


def test_detects_multiple_questions():
    message = "利用者は誰ですか？期限はいつですか？"
    assert "multiple_questions" in response_quality_issues(message)


def test_invalid_response_is_rebuilt_with_one_question():
    message = "以下の3点を確認します。\n1. 利用者は誰ですか？"
    fixed = normalize_assistant_message(message, ["利用者は誰ですか？"])
    assert fixed.count("？") == 1
    assert "以下の3点" not in fixed


def test_valid_short_response_is_unchanged():
    message = "目的を反映しました。\n\n主な利用者は誰ですか？"
    assert normalize_assistant_message(message, ["主な利用者は誰ですか？"]) == message
