"""Engage skill key — periodic repeat while a target stays engaged."""

from __future__ import annotations

from ro_bot.hunt.policies.engagement import EngagementMachine


class _Bridge:
    def __init__(self) -> None:
        self.keys: list[str] = []

    def press_key(self, key: str) -> None:
        self.keys.append(key)


class _Aim:
    last_click_at = 0.0

    def aim_and_click(self, *_args, **_kwargs) -> bool:
        return True

    def shift_timestamps(self, _delta: float) -> None:
        pass


class _Cells:
    def __init__(self, *, visible: bool = True) -> None:
        self._visible = visible

    def is_visible(self, _gid: int) -> bool:
        return self._visible

    def settled_cell(self, _gid: int, _now: float) -> tuple[int, int] | None:
        return (5, 5)


class _DeadZones:
    def contains(self, *_args) -> bool:
        return False


def _machine(
    bridge: _Bridge,
    *,
    repeat_sec: float = 0.6,
) -> EngagementMachine:
    return EngagementMachine(
        _Aim(),
        _Cells(),
        _DeadZones(),
        reaim_cooldown_sec=0.3,
        bridge=bridge,
        engage_skill_key="w",
        engage_skill_delay_sec=0.0,
        engage_skill_repeat_sec=repeat_sec,
    )


def test_repeats_skill_every_interval_while_engaged() -> None:
    bridge = _Bridge()
    machine = _machine(bridge)
    machine.state.gid = 42
    machine.state.last_engage_skill_at = 1.0
    machine.state.last_aim_cell = (5, 5)
    player = (5, 4)

    machine.continue_engagement(player, now=1.0)
    assert bridge.keys == []

    machine.continue_engagement(player, now=1.6)
    assert bridge.keys == ["w"]

    bridge.keys.clear()
    machine.continue_engagement(player, now=2.1)
    assert bridge.keys == []

    machine.continue_engagement(player, now=2.2)
    assert bridge.keys == ["w"]


def test_no_repeat_without_skill_key() -> None:
    bridge = _Bridge()
    machine = EngagementMachine(
        _Aim(),
        _Cells(),
        _DeadZones(),
        reaim_cooldown_sec=0.3,
        bridge=bridge,
    )
    machine.state.gid = 42
    machine.continue_engagement((3, 3), now=10.0)
    assert bridge.keys == []
