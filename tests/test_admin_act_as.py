"""管理者による代理操作のテスト。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.main import authenticated_owner, is_admin
from app import config


def _call(user: str, act_as: str = "", token: str | None = None):
    return authenticated_owner(
        x_karchitect_token=token if token is not None else config.INTERNAL_TOKEN,
        x_karchitect_user=user,
        x_karchitect_act_as=act_as,
    )


def test_admin_can_act_as_another_user():
    assert _call("xb_bittensor", "Yman1221442Y") == "Yman1221442Y"


def test_non_admin_cannot_act_as_another_user():
    """黙って自分のデータを操作すると代理できたと誤解される。403にする。"""
    with pytest.raises(HTTPException) as exc:
        _call("Yman1221442Y", "xb_bittensor")
    assert exc.value.status_code == 403


def test_without_act_as_the_owner_is_unchanged():
    assert _call("Yman1221442Y") == "Yman1221442Y"
    assert _call("xb_bittensor") == "xb_bittensor"


def test_act_as_self_is_allowed():
    assert _call("Yman1221442Y", "Yman1221442Y") == "Yman1221442Y"


def test_invalid_act_as_is_rejected():
    with pytest.raises(HTTPException) as exc:
        _call("xb_bittensor", "bad\x00user")
    assert exc.value.status_code == 400


def test_admin_list_contains_the_configured_admin():
    assert is_admin("xb_bittensor")
    assert not is_admin("Yman1221442Y")
