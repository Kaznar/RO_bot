"""Self-buff defer until hunt teleport."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from ro_bot.hunt.config import BuffSpec
from ro_bot.hunt.policies.buffs import SelfCastBuffPolicy


def test_self_buff_casts_after_teleport_not_mid_hunt() -> None:
    bridge = MagicMock()
    sniffer = MagicMock()
    sniffer.get_map_name.return_value = "prt_fild03"
    sniffer.get_player_pos.return_value = (100, 100)
    aim = MagicMock()
    aim.aim_and_click.return_value = True

    policy = SelfCastBuffPolicy(
        (BuffSpec(order=1, key="d", interval_sec=240),),
        bridge,
        sniffer,
        frozenset(),
        aim=aim,
        click_self=True,
        skill_delay_sec=0.0,
        active_farm_map="prt_fild03",
        farm_map_only=True,
        step_gap_sec=0.0,
    )
    policy.install()
    policy._last_cycle_at = time.monotonic() - 300.0

    now = time.monotonic()
    policy.tick(now)
    assert policy._buff_owed
    assert not policy._casting
    bridge.press_key.assert_not_called()

    policy.notify_teleport(now)
    assert policy._cast_after_teleport

    policy.tick(now + 0.1)
    assert bridge.press_key.called
    assert not policy._buff_owed
