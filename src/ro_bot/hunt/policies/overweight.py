"""Overweight: suspend hunt and press a hotbar key (e.g. storage macro).

When ``weight / weight_max >= ratio`` (from memory), the client often
cannot attack or use fly wing reliably. The controller stops targeting
and idle teleport until load drops below the ratio.
"""

from __future__ import annotations

import logging
from ro_bot.core.hid.bridge import HidBridge
from ro_bot.core.memory.player_state import PlayerState
from ro_bot.hunt.config import OverweightConfig

logger = logging.getLogger("ro_bot.hunt")


class OverweightPolicy:
    def __init__(self, cfg: OverweightConfig, bridge: HidBridge) -> None:
        self._cfg = cfg
        self._bridge = bridge
        self._last_press_at: float = 0.0

    def is_overloaded(self, state: PlayerState) -> bool:
        if not self._cfg.key:
            return False
        if state.weight_max <= 0:
            return False
        return state.weight >= self._cfg.ratio * state.weight_max

    def tick(self, now: float) -> None:
        """Press ``key`` at most once per ``press_interval_sec``."""
        if not self._cfg.key:
            return
        if now - self._last_press_at < self._cfg.press_interval_sec:
            return
        self._last_press_at = now
        try:
            self._bridge.press_key(self._cfg.key)
        except Exception:
            logger.exception(
                "HID press_key('%s') failed (overweight)", self._cfg.key,
            )
            return
        logger.warning(
            "Overweight: pressed '%s' (interval=%.1fs) — reduce load or "
            "lower weight; hunt/idle teleport suspended",
            self._cfg.key, self._cfg.press_interval_sec,
        )

    def shift(self, delta: float) -> None:
        if self._last_press_at:
            self._last_press_at += delta

    def on_map_reset(self) -> None:
        self._last_press_at = 0.0
