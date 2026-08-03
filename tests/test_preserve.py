"""確定済みの要件を1回のLLMターンで失わないための保護のテスト。"""

from __future__ import annotations

from app.engine import PRESERVED_LIST_FIELDS, preserve_existing_content
from app.models import DataEntity, Decision, Requirements


def test_emptied_data_entities_are_restored():
    """2026-08-03、5件のdata_entitiesが1応答で空になり設計書ごと消えた。"""
    previous = Requirements(
        data_entities=[DataEntity(name="取引先マスタ", key_fields=["ID", "名称"])]
    )
    incoming = Requirements(data_entities=[])
    merged = preserve_existing_content(previous, incoming)
    assert len(merged.data_entities) == 1
    assert merged.data_entities[0].name == "取引先マスタ"


def test_incoming_content_wins_when_present():
    """LLMが更新した内容は尊重する（埋め戻しは空のときだけ）。"""
    previous = Requirements(data_entities=[DataEntity(name="旧")])
    incoming = Requirements(data_entities=[DataEntity(name="新1"), DataEntity(name="新2")])
    merged = preserve_existing_content(previous, incoming)
    assert [e.name for e in merged.data_entities] == ["新1", "新2"]


def test_empty_previous_stays_empty():
    merged = preserve_existing_content(Requirements(), Requirements())
    assert merged.data_entities == []


def test_all_protected_sections_are_restored():
    previous = Requirements(
        data_entities=[DataEntity(name="E")],
        decisions=[Decision(id="D1", topic="t", decision="d")],
        constraints=["制約"],
        assumptions=["仮定"],
        in_scope=["対象"],
        target_users=["利用者"],
        raw_notes=["メモ"],
    )
    merged = preserve_existing_content(previous, Requirements())
    for name in ("data_entities", "decisions", "constraints", "assumptions",
                 "in_scope", "target_users", "raw_notes"):
        assert getattr(merged, name), f"{name} が復元されていない"


def test_protected_fields_exist_on_the_model():
    req = Requirements()
    for name in PRESERVED_LIST_FIELDS:
        assert hasattr(req, name), f"{name} は Requirements に存在しない"
