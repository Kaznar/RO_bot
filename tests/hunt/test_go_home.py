"""Go-home: ``h`` vs skill + menu."""

from __future__ import annotations

from unittest.mock import MagicMock

from ro_bot.hunt.config import GoHomeConfig
from ro_bot.hunt.policies.go_home import execute_go_home


def test_execute_skill_sequence() -> None:
    bridge = MagicMock()
    cfg = GoHomeConfig(
        method="skill",
        skill_key="v",
        skill_delay_sec=0.8,
        menu=(("down", 0.5), ("enter", 0.0)),
    )
    execute_go_home(bridge, cfg)
    assert [c.args[0] for c in bridge.press_key.call_args_list] == [
        "v", "down", "enter",
    ]


def test_execute_item_key() -> None:
    bridge = MagicMock()
    execute_go_home(bridge, GoHomeConfig(method="item", item_key="h"))
    bridge.press_key.assert_called_once_with("h")
