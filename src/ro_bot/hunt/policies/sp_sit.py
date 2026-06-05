"""Farm SP regeneration — sit (space) until memory SP is full.

Uses :class:`~ro_bot.core.memory.player_state.PlayerState` ``sp`` /
``sp_max``. Does not start while engaged, overweight, or off the active
farm map. HP drop while sitting means a mob knocked the character up — do not
press space again (already standing). When SP is full, press space to
stand; NexusRO does not auto-stand on full SP.
"""

from __future__ import annotations

import logging
import time

from ro_bot.core.hid.bridge import HidBridge
from ro_bot.core.memory.player_state import PlayerState
from ro_bot.hunt.config import SpSitConfig

logger = logging.getLogger("ro_bot.hunt")


class SpSitPolicy:
    def __init__(
        self,
        cfg: SpSitConfig,
        bridge: HidBridge,
        *,
        active_farm_map: str,
    ) -> None:
        self._cfg = cfg
        self._bridge = bridge
        self._farm_map = active_farm_map.strip()
        self._sitting = False
        self._hp_at_sit: int = 0
        self._postpone_until: float = 0.0
        #: Bot initiated sit; game may still be sitting after we lost
        #: ``_sitting`` (HP interrupt) — press space once SP is full.
        self._needs_stand_cleanup: bool = False

    def blocks_hunt(self) -> bool:
        return self._sitting

    def on_map_reset(self) -> None:
        if self._sitting:
            self._stand_up("map_reset")
        self._hp_at_sit = 0

    def shift(self, delta: float) -> None:
        if self._postpone_until > 0:
            self._postpone_until += delta

    def tick(
        self,
        now: float,
        current_map: str,
        *,
        engaged: bool,
        state: PlayerState,
    ) -> None:
        if not self._farm_map or current_map != self._farm_map:
            if self._sitting:
                logger.info("SP sit: left farm map — standing")
                self._stand_up("left_farm")
            return

        if engaged:
            if self._sitting:
                logger.info("SP sit: engaged — standing")
                self._stand_up("engaged")
            return

        if state.sp_max <= 0:
            return

        if self._too_heavy(state):
            if self._sitting:
                logger.info("SP sit: overweight — standing")
                self._stand_up("overweight")
            return

        if self._sitting:
            self._tick_while_sitting(now, state)
            return

        if now < self._postpone_until:
            return

        if state.sp >= self._cfg.sit_when_sp_below:
            self._maybe_stand_cleanup(state)
            return

        self._start_sitting(now, state)

    def _tick_while_sitting(self, now: float, state: PlayerState) -> None:
        if (
            state.hp_max > 0
            and state.hp < self._hp_at_sit - self._cfg.min_hp_drop
        ):
            logger.warning(
                "SP sit: HP %d < %d at sit start — interrupt, postpone %.0fs",
                state.hp,
                self._hp_at_sit,
                self._cfg.postpone_after_interrupt_sec,
            )
            self._end_sitting(press_stand=False)
            self._postpone_until = now + self._cfg.postpone_after_interrupt_sec
            return

        if state.sp >= state.sp_max:
            logger.info(
                "SP sit: SP full %d/%d — standing, resume hunt",
                state.sp, state.sp_max,
            )
            self._stand_up("sp_full")
            return

    def _start_sitting(self, now: float, state: PlayerState) -> None:
        if not self._press_sit_toggle("low_sp"):
            return
        self._sitting = True
        self._needs_stand_cleanup = True
        self._hp_at_sit = state.hp if state.hp_max > 0 else 0
        logger.info(
            "SP sit: sitting (SP=%d/%d, HP=%d baseline, weight=%.1f%%)",
            state.sp,
            state.sp_max,
            self._hp_at_sit,
            100.0 * state.weight / state.weight_max
            if state.weight_max > 0
            else 0.0,
        )

    def _too_heavy(self, state: PlayerState) -> bool:
        if state.weight_max <= 0:
            return False
        return state.weight >= self._cfg.max_weight_ratio * state.weight_max

    def _stand_up(self, reason: str) -> None:
        self._end_sitting(press_stand=True, reason=reason)

    def _end_sitting(self, *, press_stand: bool, reason: str = "") -> None:
        if not self._sitting:
            return
        if press_stand:
            self._press_sit_toggle(reason or "stand")
            self._needs_stand_cleanup = False
        self._sitting = False

    def _maybe_stand_cleanup(self, state: PlayerState) -> None:
        if not self._needs_stand_cleanup or state.sp < state.sp_max:
            return
        logger.info(
            "SP sit: SP full %d/%d — stand cleanup (lost sitting state)",
            state.sp,
            state.sp_max,
        )
        if self._press_sit_toggle("sp_full_cleanup"):
            self._needs_stand_cleanup = False

    def _press_sit_toggle(self, reason: str) -> bool:
        try:
            self._bridge.press_key(self._cfg.sit_key)
        except Exception:
            logger.exception(
                "HID press_key('%s') failed (sp_sit %s)",
                self._cfg.sit_key, reason,
            )
            return False
        return True
