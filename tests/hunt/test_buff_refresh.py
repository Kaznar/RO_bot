"""Buff refresh on farm entry after death / warp."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ro_bot.hunt.config import BuffSpec
from ro_bot.hunt.policies.buffs import IntervalBuffPolicy


def test_refresh_consumables_presses_and_resets_timers() -> None:
    bridge = MagicMock()
    sniffer = MagicMock()
    sniffer.get_map_name.return_value = "mjolnir_02"
    policy = IntervalBuffPolicy(
        (BuffSpec(order=1, key="f", interval_sec=100.0),),
        bridge,
        sniffer,
        frozenset(),
    )
    policy.install()
    policy.refresh_consumables(1000.0)
    bridge.press_key.assert_called_once_with("f")
    assert policy._last_at["f"] == 1000.0


def test_refresh_orders_f_then_c_with_gap() -> None:
    bridge = MagicMock()
    sniffer = MagicMock()
    policy = IntervalBuffPolicy(
        (
            BuffSpec(order=1, key="f", interval_sec=100.0),
            BuffSpec(order=2, key="c", interval_sec=50.0),
        ),
        bridge,
        sniffer,
        frozenset(),
        step_gap_sec=1.0,
    )
    with patch("ro_bot.hunt.policies.buffs.time.sleep") as sleep:
        policy.refresh_consumables(0.0)
    assert [c.args[0] for c in bridge.press_key.call_args_list] == ["f", "c"]
    sleep.assert_called_once_with(1.0)


def test_tick_presses_only_due_buff() -> None:
    bridge = MagicMock()
    sniffer = MagicMock()
    sniffer.get_map_name.return_value = "mjolnir_02"
    policy = IntervalBuffPolicy(
        (
            BuffSpec(order=1, key="f", interval_sec=100.0),
            BuffSpec(order=2, key="c", interval_sec=50.0),
        ),
        bridge,
        sniffer,
        frozenset(),
    )
    policy.install()
    policy._last_at["f"] = 50.0
    policy._last_at["c"] = 40.0
    policy.tick(100.0)
    bridge.press_key.assert_called_once_with("c")
