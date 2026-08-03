"""「次にやること」の提示のテスト。利用者が言い方を推測せずに済むこと。"""

from __future__ import annotations

from app.engine import missing_items, next_action
from app.models import (
    ArchitectureChoice, DataEntity, FunctionalRequirement,
    NonFunctionalRequirement, Requirements, Risk,
)


def _almost_done() -> Requirements:
    """リスクだけ欠けている状態(2026-08-03のテスターと同じ)。"""
    return Requirements(
        purpose="目的", target_users=["営業"], in_scope=["顧客管理"],
        functional_requirements=[
            FunctionalRequirement(id="F1", title="登録", acceptance_criteria=["登録できる"])
        ],
        non_functional_requirements=[NonFunctionalRequirement(category="性能", requirement="1秒")],
        data_entities=[DataEntity(name="取引先")],
        architecture=ArchitectureChoice(style="kintone"),
        stage="design",
    )


def test_missing_risks_is_reported():
    missing = missing_items(_almost_done())
    assert [m["key"] for m in missing] == ["risks"]
    assert missing[0]["label"] == "リスクと対策"
    assert missing[0]["prompt"]  # そのまま送れる依頼文


def test_advance_button_is_offered_with_the_exact_wording():
    """「レビューに進んでください」を利用者が思いつく必要をなくす。"""
    action = next_action(_almost_done())
    assert action["next_stage"] == "review"
    assert action["advance"] is not None
    assert "review" in action["advance"]["prompt"]


def test_nothing_missing_offers_only_advance():
    req = _almost_done()
    req.risks = [Risk(title="移行時のデータ欠落")]
    action = next_action(req)
    assert action["missing"] == []
    assert action["advance"]["stage"] == "review"


def test_ready_has_no_next_stage():
    req = _almost_done()
    req.risks = [Risk(title="r")]
    req.stage = "ready"
    action = next_action(req)
    assert action["next_stage"] is None
    assert action["advance"] is None


def test_empty_project_lists_many_missing_items():
    action = next_action(Requirements())
    keys = [m["key"] for m in action["missing"]]
    assert "purpose" in keys and "functional_requirements" in keys


def test_checklist_shows_all_ten_items_with_status():
    """未達だけ出すと、判定根拠が画面に無いまま項目名だけ現れて意味が通らない。"""
    action = next_action(_almost_done())
    items = action["checklist"]
    assert len(items) == 10
    assert all("done" in i and "label" in i for i in items)
    done = {i["key"]: i["done"] for i in items}
    assert done["risks"] is False
    assert done["data_entities"] is True
    assert done["functional_requirements"] is True


def test_checklist_and_missing_are_consistent():
    action = next_action(_almost_done())
    assert [i["key"] for i in action["checklist"] if not i["done"]] == [
        i["key"] for i in action["missing"]
    ]
