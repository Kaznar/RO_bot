"""Hotbar buff policies — interval keys (``f``/``c``) and self-cast cycle (``a``/``d``).

* :class:`IntervalBuffPolicy` — one key press per ``interval_sec`` on any hunt map.
* :class:`SelfCastBuffPolicy` — ordered hotkey → self LMB on farm map; when the
  interval elapses, the cycle waits for the next hunt teleport (``t`` / escape)
  instead of casting mid-combat.
* :class:`BuffPolicy` — runs both; ``is_busy`` only during self-cast.
"""

from __future__ import annotations

import logging
import time

from ro_bot.core.hid.bridge import HidBridge
from ro_bot.core.network.sniffer import PacketSniffer
from ro_bot.hunt.aim_service import AimService
from ro_bot.hunt.config import BuffSpec

logger = logging.getLogger("ro_bot.hunt")


class IntervalBuffPolicy:
    """Per-key interval press (legacy ``f`` / ``c`` consumables)."""

    def __init__(
        self,
        buffs: tuple[BuffSpec, ...],
        bridge: HidBridge,
        sniffer: PacketSniffer,
        manual_control_maps: frozenset[str],
        *,
        all_maps: bool = False,
        step_gap_sec: float = 1.0,
    ) -> None:
        self._ordered = tuple(sorted(buffs, key=lambda b: b.order))
        self._bridge = bridge
        self._sniffer = sniffer
        self._manual_control_maps = manual_control_maps
        self._all_maps = all_maps
        self._step_gap_sec = max(0.0, step_gap_sec)
        self._last_at: dict[str, float] = {}

    def install(self) -> None:
        now = time.monotonic()
        self._last_at = {b.key: now for b in self._ordered}

    def uninstall(self) -> None:
        self._last_at.clear()

    def tick(self, now: float) -> None:
        if not self._last_at or not self._consumables_ok():
            return
        due = [
            buff for buff in self._ordered
            if self._is_due(buff, now)
        ]
        self._press_ordered(due, now, action="pressed")

    def mark_pressed(self, key: str, now: float) -> None:
        if key in self._last_at:
            self._last_at[key] = now

    def refresh_consumables(self, now: float) -> None:
        """Re-apply interval buffs and restart timers (e.g. after death)."""
        if not self._ordered:
            return
        self._press_ordered(list(self._ordered), now, action="refreshed")

    def _is_due(self, buff: BuffSpec, now: float) -> bool:
        last = self._last_at.get(buff.key)
        return last is not None and now - last >= buff.interval_sec

    def _press_ordered(
        self,
        buffs: list[BuffSpec],
        now: float,
        *,
        action: str,
    ) -> None:
        for i, buff in enumerate(buffs):
            try:
                self._bridge.press_key(buff.key)
            except Exception:
                logger.exception(
                    "HID press_key('%s') failed (interval buff %s)",
                    buff.key, action,
                )
                continue
            self._last_at[buff.key] = now
            logger.info(
                "Buff: %s '%s' (next in %.0fs)",
                action, buff.key, buff.interval_sec,
            )
            if i < len(buffs) - 1 and self._step_gap_sec > 0:
                time.sleep(self._step_gap_sec)

    def shift(self, delta: float) -> None:
        if self._last_at:
            self._last_at = {k: t + delta for k, t in self._last_at.items()}

    def _consumables_ok(self) -> bool:
        name = self._sniffer.get_map_name()
        if name is None:
            return False
        if self._all_maps:
            return True
        return name not in self._manual_control_maps


class SelfCastBuffPolicy:
    """``d`` → self click → gap → ``a`` → self click on ``active_farm_map``."""

    def __init__(
        self,
        steps: tuple[BuffSpec, ...],
        bridge: HidBridge,
        sniffer: PacketSniffer,
        manual_control_maps: frozenset[str],
        *,
        aim: AimService | None = None,
        click_self: bool = True,
        skill_delay_sec: float = 0.2,
        all_maps: bool = False,
        healer_suppress_sec: float = 0.0,
        active_farm_map: str = "",
        farm_map_only: bool = True,
        step_gap_sec: float = 1.0,
    ) -> None:
        ordered = tuple(sorted(steps, key=lambda b: b.order))
        self._sequence = ordered
        self._bridge = bridge
        self._sniffer = sniffer
        self._aim = aim
        self._click_self = click_self and aim is not None
        if click_self and aim is None:
            logger.warning(
                "Self-buff click_self requires AimService — key-only fallback",
            )
        self._skill_delay_sec = max(0.0, skill_delay_sec)
        self._manual_control_maps = manual_control_maps
        self._all_maps = all_maps
        self._healer_suppress_sec = max(0.0, healer_suppress_sec)
        self._active_farm_map = active_farm_map.strip()
        self._farm_map_only = farm_map_only
        self._step_gap_sec = max(0.0, step_gap_sec)
        self._interval_sec = ordered[0].interval_sec if ordered else 0.0
        self._sequence_keys = frozenset(b.key for b in ordered)
        self._last_cycle_at: float = 0.0
        self._suppress_until: float = 0.0
        self._casting: bool = False
        #: Interval elapsed — wait for hunt teleport instead of casting in combat.
        self._buff_owed: bool = False
        #: Teleport fired — cast on the next tick on the farm map.
        self._cast_after_teleport: bool = False

    def enabled(self) -> bool:
        return bool(self._sequence)

    def install(self) -> None:
        self._last_cycle_at = time.monotonic()
        self._casting = False
        self._buff_owed = False
        self._cast_after_teleport = False

    def uninstall(self) -> None:
        self._last_cycle_at = 0.0
        self._suppress_until = 0.0
        self._casting = False
        self._buff_owed = False
        self._cast_after_teleport = False

    def is_busy(self) -> bool:
        return self._casting

    def suppress_after_healer(self, now: float) -> None:
        if self._healer_suppress_sec <= 0:
            return
        self._suppress_until = now + self._healer_suppress_sec
        self._casting = False
        self._cast_after_teleport = False
        logger.info(
            "Self-buff: healer done — paused for %.0fs",
            self._healer_suppress_sec,
        )

    def notify_teleport(self, now: float) -> None:
        """Queue a owed buff cycle for the next farm tick after a hunt teleport."""
        if not self._buff_owed:
            return
        self._cast_after_teleport = True
        logger.info(
            "Self-buff: teleport — casting a/d after warp (owed %.0fs)",
            now - self._last_cycle_at,
        )

    def _cycle_due(self, now: float) -> bool:
        return (
            self._interval_sec > 0
            and now - self._last_cycle_at >= self._interval_sec
        )

    def tick(self, now: float) -> None:
        if self._casting or not self._sequence:
            return
        if now < self._suppress_until:
            return
        if self._interval_sec <= 0:
            return
        if not self._consumables_ok(now):
            return

        if self._cast_after_teleport:
            self._casting = True
            try:
                if self._run_cycle(now):
                    self._buff_owed = False
                    self._cast_after_teleport = False
                    logger.info(
                        "Self-buff: post-teleport cycle done (next in %.0fs)",
                        self._interval_sec,
                    )
            finally:
                self._casting = False
            return

        if self._cycle_due(now):
            if not self._buff_owed:
                logger.info(
                    "Self-buff: cycle due — deferred until teleport",
                )
            self._buff_owed = True

    def _run_cycle(self, now: float) -> bool:
        for i, step in enumerate(self._sequence):
            if not self._cast_step(step.key):
                logger.warning(
                    "Self-buff: aborted at '%s' (%d/%d)",
                    step.key, i + 1, len(self._sequence),
                )
                return False
            if i < len(self._sequence) - 1:
                time.sleep(self._step_gap_sec)
        self._last_cycle_at = now
        return True

    def _cast_step(self, key: str) -> bool:
        try:
            self._bridge.press_key(key)
        except Exception:
            logger.exception("HID press_key('%s') failed (self-buff)", key)
            return False
        if not self._click_self:
            logger.info("Self-buff: pressed '%s' (key only)", key)
            return True
        px, py = self._sniffer.get_player_pos()
        if px <= 0 and py <= 0:
            logger.warning(
                "Self-buff: no player position — skip click for '%s'", key,
            )
            return False
        player_cell = (px, py)
        if self._skill_delay_sec > 0:
            time.sleep(self._skill_delay_sec)
        assert self._aim is not None
        if not self._aim.aim_and_click(
            player_cell, player_cell, target_name=None,
        ):
            logger.warning(
                "Self-buff: '%s' ok but self click failed (dead zone?)", key,
            )
            return False
        logger.info("Self-buff: '%s' + self click", key)
        return True

    def _consumables_ok(self, now: float) -> bool:
        if now < self._suppress_until:
            return False
        name = self._sniffer.get_map_name()
        if name is None:
            return False
        if (
            self._farm_map_only
            and self._active_farm_map
            and name != self._active_farm_map
        ):
            return False
        if self._all_maps:
            return True
        return name not in self._manual_control_maps

    def mark_pressed(self, key: str, now: float) -> None:
        if key in self._sequence_keys:
            self._last_cycle_at = now
            self._casting = False
            self._buff_owed = False
            self._cast_after_teleport = False

    def shift(self, delta: float) -> None:
        if self._suppress_until > 0:
            self._suppress_until += delta
        if self._last_cycle_at > 0:
            self._last_cycle_at += delta


class BuffPolicy:
    """Interval buffs + optional self-cast cycle."""

    def __init__(
        self,
        buffs: tuple[BuffSpec, ...],
        bridge: HidBridge,
        sniffer: PacketSniffer,
        manual_control_maps: frozenset[str],
        *,
        self_buffs: tuple[BuffSpec, ...] = (),
        aim: AimService | None = None,
        click_self: bool = True,
        skill_delay_sec: float = 0.2,
        all_maps: bool = False,
        healer_suppress_sec: float = 0.0,
        active_farm_map: str = "",
        farm_map_only: bool = True,
        step_gap_sec: float = 1.0,
    ) -> None:
        self._interval = (
            IntervalBuffPolicy(
                buffs,
                bridge,
                sniffer,
                manual_control_maps,
                all_maps=all_maps,
                step_gap_sec=step_gap_sec,
            )
            if buffs else None
        )
        self._self_cast = (
            SelfCastBuffPolicy(
                self_buffs,
                bridge,
                sniffer,
                manual_control_maps,
                aim=aim,
                click_self=click_self,
                skill_delay_sec=skill_delay_sec,
                all_maps=all_maps,
                healer_suppress_sec=healer_suppress_sec,
                active_farm_map=active_farm_map,
                farm_map_only=farm_map_only,
                step_gap_sec=step_gap_sec,
            )
            if self_buffs else None
        )

    def install(self) -> None:
        if self._interval is not None:
            self._interval.install()
        if self._self_cast is not None:
            self._self_cast.install()

    def uninstall(self) -> None:
        if self._interval is not None:
            self._interval.uninstall()
        if self._self_cast is not None:
            self._self_cast.uninstall()

    def is_busy(self) -> bool:
        return (
            self._self_cast is not None
            and self._self_cast.is_busy()
        )

    def suppress_after_healer(self, now: float) -> None:
        if self._self_cast is not None:
            self._self_cast.suppress_after_healer(now)

    def notify_teleport(self, now: float) -> None:
        if self._self_cast is not None:
            self._self_cast.notify_teleport(now)

    def tick(self, now: float) -> None:
        if self._interval is not None:
            self._interval.tick(now)
        if self._self_cast is not None:
            self._self_cast.tick(now)

    def mark_pressed(self, key: str, now: float) -> None:
        if self._interval is not None:
            self._interval.mark_pressed(key, now)
        if self._self_cast is not None:
            self._self_cast.mark_pressed(key, now)

    def shift(self, delta: float) -> None:
        if self._interval is not None:
            self._interval.shift(delta)
        if self._self_cast is not None:
            self._self_cast.shift(delta)
