from __future__ import annotations

import html
import json
import re
from pathlib import Path

import markdown
from weasyprint import HTML

from .config import STATIC_DIR, TEMPLATES_DIR
from .engine import completeness
from .models import Requirements


def _bullets(items: list[str], empty: str = "未定") -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {empty}"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = [
        "| " + " | ".join(str(cell).replace("|", "｜").replace("\n", "<br>") for cell in row) + " |"
        for row in rows
    ]
    return "\n".join([head, separator, *body])


def _entity_field_names(entity) -> list[str]:
    """概要表に出す項目名。詳細定義があればそちらを、無ければ従来のkey_fieldsを使う。"""
    if entity.fields:
        return [field.name for field in entity.fields]
    return list(entity.key_fields)


def _entity_field_tables(req) -> str:
    """エンティティごとのフィールド詳細定義。実装できる粒度で出す。

    fields が空のエンティティは表を出さない（従来どおり概要表だけになる）。
    """
    blocks: list[str] = []
    for entity in req.data_entities:
        if not entity.fields:
            continue
        rows = [
            [
                field.name,
                field.code or "—",
                field.type or "—",
                "必須" if field.required else "任意",
                "<br>".join(field.options) or "—",
                field.default or "—",
                field.reference or "—",
                field.note or "—",
            ]
            for field in entity.fields
        ]
        blocks.append(
            f"#### {entity.name}\n\n"
            + _table(
                ["フィールド名", "フィールドコード", "型", "必須", "選択肢", "初期値", "参照先", "備考"],
                rows,
            )
        )
    if not blocks:
        return "フィールドの詳細定義はまだありません。"
    return "\n\n".join(blocks)


def _safe_mermaid(value: str) -> str:
    return re.sub(r'["\[\]{}()]', "", value).strip()[:50] or "未定"


def build_markdown(req: Requirements) -> str:
    functional_rows = [
        [
            item.id,
            item.priority,
            item.title,
            item.description or "—",
            "<br>".join(item.acceptance_criteria) or "要確認",
            item.status,
        ]
        for item in req.functional_requirements
    ]
    nfr_rows = [
        [item.category, item.requirement, item.target or "要確認", item.priority, item.status]
        for item in req.non_functional_requirements
    ]
    question_rows = [
        [item.id, item.importance, item.category, item.question, item.answer or "未回答", item.status]
        for item in req.open_questions
    ]
    entity_rows = [
        [
            item.name,
            item.purpose or "—",
            "<br>".join(_entity_field_names(item)) or "要設計",
            "対象" if item.sensitive else "—",
        ]
        for item in req.data_entities
    ]
    entity_detail = _entity_field_tables(req)
    decision_rows = [
        [item.id, item.topic, item.decision, item.rationale or "—", item.status]
        for item in req.decisions
    ]
    risk_rows = [[item.title, item.impact or "要評価", item.mitigation or "要検討"] for item in req.risks]

    user_nodes = "\n".join(
        f'    U{index}["{_safe_mermaid(user)}"]'
        for index, user in enumerate(req.target_users[:5], 1)
    ) or '    U1["利用者未定"]'
    user_edges = "\n".join(
        f"    U{index} --> WEB"
        for index, _ in enumerate(req.target_users[:5], 1)
    ) or "    U1 --> WEB"
    frontend = _safe_mermaid(req.architecture.frontend or "Web UI")
    backend = _safe_mermaid(req.architecture.backend or "Application API")
    database = _safe_mermaid(req.architecture.database or "Database")
    integration_nodes = "\n".join(
        f'    X{index}["{_safe_mermaid(item.name)}"]'
        for index, item in enumerate(req.integrations[:5], 1)
    )
    integration_edges = "\n".join(
        f"    API --> X{index}"
        for index, _ in enumerate(req.integrations[:5], 1)
    )

    return f"""# {req.project_name or "名称未定"} システム設計書

> Kurage Architect revision {req.revision} / 完成度 {completeness(req)}% / 工程 `{req.stage}`

## 1. 概要

### 1.1 要約

{req.summary or "未定"}

### 1.2 目的

{req.purpose or "未定"}

### 1.3 背景

{req.background or "未定"}

## 2. 利用者とステークホルダー

### 2.1 対象利用者

{_bullets(req.target_users)}

### 2.2 ステークホルダー

{_bullets(req.stakeholders)}

### 2.3 ユーザーストーリー

{_bullets(req.user_stories)}

## 3. スコープ

### 3.1 対象

{_bullets(req.in_scope)}

### 3.2 対象外

{_bullets(req.out_of_scope)}

## 4. 機能要件

{_table(["ID", "優先度", "機能", "説明", "受入条件", "状態"], functional_rows) if functional_rows else "機能要件は未定です。"}

## 5. 非機能要件

{_table(["分類", "要件", "目標値", "優先度", "状態"], nfr_rows) if nfr_rows else "非機能要件は未定です。"}

## 6. システム構成

```mermaid
flowchart LR
{user_nodes}
    WEB["{frontend}"]
    API["{backend}"]
    DB[("{database}")]
{integration_nodes}
{user_edges}
    WEB --> API
    API --> DB
{integration_edges}
```

### 6.1 アーキテクチャ選択

- 方式: {req.architecture.style or "未定"}
- フロントエンド: {req.architecture.frontend or "未定"}
- バックエンド: {req.architecture.backend or "未定"}
- データベース: {req.architecture.database or "未定"}
- インフラ: {req.architecture.infrastructure or "未定"}
- 認証方式: {req.architecture.authentication or "未定"}

## 7. データ設計

{_table(["エンティティ", "目的", "主要フィールド", "機微情報"], entity_rows) if entity_rows else "データエンティティは未定です。"}

### 7.1 フィールド定義

{entity_detail}

```mermaid
classDiagram
{_class_diagram(req)}
```

## 8. 外部連携

{_table(["サービス", "目的", "方式", "状態"], [[i.name, i.purpose or "—", i.protocol or "未定", i.status] for i in req.integrations]) if req.integrations else "外部連携はありません、または未定です。"}

## 9. 主要シーケンス

```mermaid
sequenceDiagram
    actor User as 利用者
    participant UI as {frontend}
    participant API as {backend}
    participant DB as {database}
    User->>UI: 操作
    UI->>API: リクエスト
    API->>DB: 検証・保存・取得
    DB-->>API: 結果
    API-->>UI: 応答
    UI-->>User: 結果表示
```

## 10. 制約と仮定

### 10.1 制約

{_bullets(req.constraints)}

### 10.2 仮定

{_bullets(req.assumptions)}

## 11. 設計上の決定

{_table(["ID", "論点", "決定", "理由", "状態"], decision_rows) if decision_rows else "設計上の決定は未登録です。"}

## 12. リスク

{_table(["リスク", "影響", "対策"], risk_rows) if risk_rows else "リスクは未登録です。"}

## 13. 未決事項

{_table(["ID", "重要度", "分類", "質問", "回答", "状態"], question_rows) if question_rows else "未決事項はありません。"}

## 14. 実装・テスト方針

- P0機能から受入条件単位で実装・検証する。
- API、データモデル、権限境界を自動テストする。
- 主要ユーザーストーリーをE2Eテストへ落とし込む。
- 性能・可用性・バックアップの目標値が確定後、非機能テストを追加する。

## 15. 要件メモ

{_bullets(req.raw_notes)}
"""


def _class_diagram(req: Requirements) -> str:
    if not req.data_entities:
        return '    class 未定 {\n      +String id\n    }'
    chunks = []
    for entity in req.data_entities[:12]:
        chunks.append(f"    class {_safe_mermaid(entity.name).replace(' ', '_')} {{")
        names = _entity_field_names(entity)
        for field in names[:12]:
            chunks.append(f"      +String {_safe_mermaid(field).replace(' ', '_')}")
        if not names:
            chunks.append("      +String id")
        chunks.append("    }")
    return "\n".join(chunks)


def render_html(markdown_text: str, title: str) -> str:
    body = markdown.markdown(
        markdown_text,
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
    )
    template = (TEMPLATES_DIR / "design.html").read_text(encoding="utf-8")
    return template.replace("{{TITLE}}", html.escape(title)).replace("{{CONTENT}}", body)


def render_pdf(markdown_text: str, title: str, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    rendered = render_html(markdown_text, title)
    HTML(string=rendered, base_url=str(STATIC_DIR.parent)).write_pdf(output)
    return output


def requirements_json(req: Requirements) -> str:
    return json.dumps(req.model_dump(mode="json"), ensure_ascii=False, indent=2)

