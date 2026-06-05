"""Death return: esc only from attempt 2, max attempts cap."""

from __future__ import annotations

from unittest.mock import MagicMock

from ro_bot.hunt.config import DeathReturnConfig
from ro_bot.hunt.policies.death_return import DeathReturnPolicy


def _policy(max_attempts: int = 10) -> DeathReturnPolicy:
    aim = MagicMock()
    aim.aim_and_click.return_value = True
    return DeathReturnPolicy(
        DeathReturnConfig(
            town_return_retry_sec=0.0,
            town_return_max_attempts=max_attempts,
            town_return_escape_key="esc",
        ),
        MagicMock(),
        aim,
        MagicMock(),
        frozenset({"prontera"}),
    )


def test_first_attempt_no_esc() -> None:
    bridge = MagicMock()
    p = _policy()
    p._bridge = bridge
    p._sniffer.get_player_pos.return_value = (100, 100)
    p._sniffer.get_player_hp.return_value = (1, 1000)
    st = MagicMock()
    st.hp, st.hp_max, st.x, st.y = 1, 1000, 100, 100
    assert p._start_return_sequence(0.0, "mjolnir_02", st, reason="critical")
    bridge.press_key.assert_not_called()
    assert p._attempt_count == 1


def test_second_attempt_presses_esc() -> None:
    bridge = MagicMock()
    p = _policy()
    p._bridge = bridge
    p._attempt_count = 1
    p._walk_click_latched = True
    p._walk_clicked_at = 0.0
    p._maybe_town_return_retry(1.0, "mjolnir_02", None)
    bridge.press_key.assert_called_once_with("esc")
    assert p._attempt_count == 2


def test_stops_at_max_attempts() -> None:
    p = _policy(max_attempts=3)
    p._attempt_count = 3
    p._walk_click_latched = True
    p._walk_clicked_at = 0.0
    assert not p._maybe_town_return_retry(10.0, "mjolnir_02", None)
    assert not p._walk_click_latched
