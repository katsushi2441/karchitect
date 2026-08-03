"""データエンティティのフィールド詳細定義（実装できる粒度）のテスト。"""

from __future__ import annotations

import json

from app.documents import build_markdown
from app.models import DataEntity, EntityField, Requirements

FIELDS = [
    EntityField(
        name="取引先ID",
        code="account_id",
        type="自動採番",
        required=True,
        default="",
        reference="",
        note="重複禁止",
    ),
    EntityField(
        name="役割",
        code="role",
        type="複数選択",
        required=True,
        options=["顧客", "紹介者"],
        reference="",
    ),
    EntityField(
        name="紹介元取引先",
        code="referrer_id",
        type="ルックアップ",
        reference="取引先マスタ",
    ),
]


def _req_with_fields() -> Requirements:
    return Requirements(
        project_name="顧客管理",
        data_entities=[
            DataEntity(name="取引先マスタ", purpose="顧客と紹介者", fields=FIELDS),
        ],
    )


def test_field_table_is_rendered_with_implementation_columns():
    """利用者が求めるのは実装できる粒度。名前の羅列だけでは足りない。"""
    doc = build_markdown(_req_with_fields())
    assert "### 7.1 フィールド定義" in doc
    assert "#### 取引先マスタ" in doc
    assert "| フィールド名 | フィールドコード | 型 | 必須 | 選択肢 | 初期値 | 参照先 | 備考 |" in doc
    assert "| 取引先ID | account_id | 自動採番 | 必須 |" in doc
    assert "顧客<br>紹介者" in doc  # 選択肢
    assert "ルックアップ" in doc and "取引先マスタ" in doc  # 参照関係


def test_optional_field_is_marked_as_optional():
    doc = build_markdown(_req_with_fields())
    assert "| 紹介元取引先 | referrer_id | ルックアップ | 任意 |" in doc


def test_summary_table_uses_detailed_field_names():
    doc = build_markdown(_req_with_fields())
    assert "取引先ID<br>役割<br>紹介元取引先" in doc


def test_legacy_key_fields_still_render():
    """既存プロジェクトは key_fields しか持たない。壊してはいけない。"""
    req = Requirements(
        data_entities=[DataEntity(name="商材マスタ", key_fields=["商材ID", "商材名"])]
    )
    doc = build_markdown(req)
    assert "商材ID<br>商材名" in doc
    # 詳細定義が無いエンティティは表を出さない
    assert "フィールドの詳細定義はまだありません。" in doc


def test_existing_requirements_json_still_validates():
    """fields を後から足したので、既存の requirements_json が読めること。"""
    legacy = {
        "project_name": "既存",
        "data_entities": [
            {"name": "取引先", "purpose": "顧客", "key_fields": ["ID", "名称"], "sensitive": False}
        ],
        "stage": "specify",
        "revision": 3,
    }
    req = Requirements.model_validate(json.loads(json.dumps(legacy)))
    assert req.data_entities[0].fields == []
    assert req.data_entities[0].key_fields == ["ID", "名称"]


def test_class_diagram_uses_detailed_fields():
    doc = build_markdown(_req_with_fields())
    assert "classDiagram" in doc
    assert "取引先ID" in doc


def test_schema_exposes_field_definition_to_the_llm():
    """LLMに渡すJSON Schemaに fields が含まれないと、そもそも埋められない。"""
    from app.models import ChatTurnOutput

    schema = json.dumps(ChatTurnOutput.model_json_schema(), ensure_ascii=False)
    assert "EntityField" in schema
    for key in ("code", "required", "options", "reference"):
        assert f'"{key}"' in schema
