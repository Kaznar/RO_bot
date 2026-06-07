"""Go-home: ``h`` vs skill + menu."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ro_bot.hunt.config import GoHomeConfig
from ro_bot.hunt.policies.go_home import execute_go_home


def test_execute_skill_sequence() -> None:
    bridge = MagicMock()
    cfg = GoHomeConfig(
        method="skill",
        skill_key="v",
        skill_delay_sec=0.8,
        step_delay_sec=0.8,
        menu=(("down", 0.8), ("enter", 0.8)),
    )
    with patch("ro_bot.hunt.policies.go_home.time.sleep") as sleep:
        execute_go_home(bridge, cfg)
    assert [c.args[0] for c in bridge.press_key.call_args_list] == [
        "v", "down", "enter",
    ]
    assert sleep.call_args_list == [
        ((0.8,),),
        ((0.8,),),
        ((0.8,),),
    ]


def test_execute_skill_sequence_dismisses_chat_first() -> None:
    bridge = MagicMock()
    cfg = GoHomeConfig(
        method="skill",
        skill_key="v",
        step_delay_sec=0.8,
        dismiss_chat_probe_client=(176, 887),
        menu=(("down", 0.8), ("enter", 0.8)),
    )
    with (
        patch(
            "ro_bot.hunt.policies.go_home.is_chat_input_visible",
            return_value=True,
        ),
        patch("ro_bot.hunt.policies.go_home.time.sleep") as sleep,
    ):
        execute_go_home(bridge, cfg, game_hwnd=123)
    assert [c.args[0] for c in bridge.press_key.call_args_list] == [
        "escape", "v", "down", "enter",
    ]
    assert sleep.call_args_list == [
        ((0.8,),),
        ((0.8,),),
        ((0.8,),),
        ((0.8,),),
    ]


def test_execute_item_key() -> None:
    bridge = MagicMock()
    execute_go_home(bridge, GoHomeConfig(method="item", item_key="h"))
    bridge.press_key.assert_called_once_with("h")


def test_execute_skill_prepends_sp_regen_when_low() -> None:
    bridge = MagicMock()
    cfg = GoHomeConfig(
        method="skill",
        skill_key="v",
        step_delay_sec=0.8,
        sp_regen_item_key="f1",
        skill_min_sp=10,
        menu=(("down", 0.8), ("enter", 0.8)),
    )
    with patch("ro_bot.hunt.policies.go_home.time.sleep"):
        execute_go_home(bridge, cfg, current_sp=5)
    assert [c.args[0] for c in bridge.press_key.call_args_list] == [
        "f1", "v", "down", "enter",
    ]


def test_execute_skill_skips_sp_regen_when_enough_sp() -> None:
    bridge = MagicMock()
    cfg = GoHomeConfig(
        method="skill",
        skill_key="v",
        sp_regen_item_key="f1",
        skill_min_sp=10,
        menu=(("enter", 0.0),),
    )
    with patch("ro_bot.hunt.policies.go_home.time.sleep"):
        execute_go_home(bridge, cfg, current_sp=10)
    assert [c.args[0] for c in bridge.press_key.call_args_list] == ["v", "enter"]
