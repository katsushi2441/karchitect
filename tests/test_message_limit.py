"""会話1発話の文字数上限のテスト。ドキュメント貼り付けを受け付けない。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import MESSAGE_MAX_CHARS, MessageCreate


def test_conversational_length_is_accepted():
    MessageCreate(content="利用者は営業担当1〜2名と経営層です。")


def test_document_paste_is_rejected():
    """設計書を丸ごと貼られると要件が肥大しLLMの再出力が破綻する。"""
    with pytest.raises(ValidationError):
        MessageCreate(content="あ" * (MESSAGE_MAX_CHARS + 1))


def test_limit_is_conversational():
    assert MESSAGE_MAX_CHARS <= 256


def test_empty_is_rejected():
    with pytest.raises(ValidationError):
        MessageCreate(content="")
