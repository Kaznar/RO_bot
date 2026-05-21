"""Post-route buff / key sequence on ``active_farm_map``.

Armed when :class:`~ro_bot.hunt.policies.farm_home_route.FarmHomeRoutePolicy`
completes successfully. Runs before interval :class:`BuffPolicy` presses so
return-from-town buffs are not doubled.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from ro_bot.core.hid.bridge import HidBridge
from ro_bot.hunt.config import HomePrepStep

logger = logging.getLogger("ro_bot.hunt")


class FarmArrivalPolicy:
    """Ordered key presses after the home→farm click path finishes."""

    def __init__(
        self,
        steps: tuple[HomePrepStep, ...],
        bridge: HidBridge,
        active_farm_map: str,
        *,
        on_key_pressed: Callable[[str, float], None] | None = None,
    ) -> None:
        self._steps = steps
        self._bridge = bridge
        self._active_farm_map = active_farm_map.strip()
        self._on_key_pressed = on_key_pressed
        self._armed = False
        self._step_idx = 0
        self._next_at: float | None = None

    def enabled(self) -> bool:
        return bool(self._steps) and bool(self._active_farm_map)

    def is_active(self) -> bool:
        return self._armed

    def arm(self) -> None:
        if not self.enabled():
            return
        self._armed = True
        self._step_idx = 0
        self._next_at = None
        logger.info(
            "Farm arrival: armed (%d steps on '%s')",
            len(self._steps),
            self._active_farm_map,
        )

    def disarm(self) -> None:
        if not self._armed:
            return
        self._armed = False
        self._step_idx = 0
        self._next_at = None
        logger.info("Farm arrival: disarmed")

    def shift(self, delta: float) -> None:
        if self._next_at is not None:
            self._next_at += delta

    def tick(self, now: float, current_map: str) -> None:
        if not self._armed or not self.enabled():
            return
        if current_map != self._active_farm_map:
            return
        if self._step_idx >= len(self._steps):
            self._finish()
            return
        if self._next_at is not None and now < self._next_at:
            return

        step = self._steps[self._step_idx]
        total = len(self._steps)
        idx = self._step_idx

        if step.key:
            try:
                self._bridge.press_key(step.key)
            except Exception:
                logger.exception(
                    "Farm arrival: press_key('%s') failed", step.key,
                )
                return
            logger.info(
                "Farm arrival: pressed '%s' (step %d/%d)",
                step.key,
                idx + 1,
                total,
            )
            if self._on_key_pressed is not None:
                self._on_key_pressed(step.key, now)
        elif step.delay_after_sec > 0:
            logger.info(
                "Farm arrival: delay only step %d/%d (%.1fs)",
                idx + 1,
                total,
                step.delay_after_sec,
            )

        self._step_idx += 1
        if self._step_idx >= len(self._steps):
            self._finish()
        else:
            self._next_at = now + max(0.0, step.delay_after_sec)

    def _finish(self) -> None:
        self._armed = False
        self._step_idx = 0
        self._next_at = None
        logger.info("Farm arrival: finished")
