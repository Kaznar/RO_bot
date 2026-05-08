"""Aim + click façade on top of CameraProjection + HidBridge.

Translates a mob cell to a clamped screen pixel, sends a relative
mouse move to the HID bridge, settles, and emits a click. Tracks the
last click timestamp so callers can enforce re-click cooldowns.
"""

from __future__ import annotations

import logging
import time

from ro_bot.core.hid.bridge import HidBridge
from ro_bot.core.projection.camera import CameraProjection, clamp_to_rect
from ro_bot.core.window import WindowRect, get_cursor_pos
from ro_bot.hunt.config import AimOffsetSpec

logger = logging.getLogger(__name__)


class AimService:
    """Aim & click driver. One instance per hunt session."""

    def __init__(
        self,
        bridge: HidBridge,
        projection: CameraProjection,
        rect: WindowRect,
        aim_settle_sec: float,
        aim_offsets: tuple[AimOffsetSpec, ...] = (),
    ) -> None:
        self._bridge = bridge
        self._projection = projection
        self._rect = rect
        self._aim_settle_sec = aim_settle_sec
        aim_map: dict[str, float] = {}
        for spec in aim_offsets:
            for n in spec.names:
                aim_map[n] = spec.y_offset_cells
        self._aim_offsets = aim_map
        self._last_click_at: float = 0.0

    @property
    def last_click_at(self) -> float:
        return self._last_click_at

    def move(
        self,
        player_cell: tuple[int, int],
        mob_cell: tuple[int, int],
        target_name: str | None = None,
    ) -> None:
        """Relative mouse move from current cursor to ``mob_cell``'s pixel."""
        y_offset = (
            self._aim_offsets.get(target_name, 0.0)
            if target_name is not None
            else 0.0
        )
        if target_name is not None and y_offset != 0.0:
            logger.debug(
                "Aim offset: name='%s' y_offset_cells=%.2f",
                target_name, y_offset,
            )
        target_cell = (mob_cell[0], mob_cell[1] + y_offset)
        target_px = self._projection.map_to_screen(
            player_cell, target_cell, self._rect,
        )
        clamped = clamp_to_rect(target_px, self._rect)
        cursor = get_cursor_pos()
        dx = clamped[0] - cursor[0]
        dy = clamped[1] - cursor[1]
        if dx == 0 and dy == 0:
            return
        try:
            self._bridge.move_mouse(dx, dy)
        except Exception:
            logger.exception("move_mouse failed")

    def click(self) -> None:
        """Left-click and bump the click timestamp."""
        try:
            self._bridge.mouse_click()
            self._last_click_at = time.monotonic()
        except Exception:
            logger.exception("mouse_click failed")

    def aim_and_click(
        self,
        player_cell: tuple[int, int],
        mob_cell: tuple[int, int],
        target_name: str | None = None,
    ) -> None:
        """Move → settle → click, in one call."""
        self.move(player_cell, mob_cell, target_name=target_name)
        time.sleep(self._aim_settle_sec)
        self.click()

    def shift_timestamps(self, delta: float) -> None:
        """Pause/resume support: slide ``last_click_at`` by ``delta``."""
        if self._last_click_at:
            self._last_click_at += delta
