"""Aim + click façade on top of CameraProjection + HidBridge.

Translates a mob cell to a clamped screen pixel, sends a relative
mouse move to the HID bridge, settles, and emits a click. Tracks the
last click timestamp so callers can enforce re-click cooldowns.
"""

from __future__ import annotations

import logging
import random
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

    def set_client_rect(self, rect: WindowRect) -> None:
        """Refresh client→screen mapping (e.g. after the game window moved)."""
        self._rect = rect

    @property
    def last_click_at(self) -> float:
        return self._last_click_at

    def move(
        self,
        player_cell: tuple[int, int],
        mob_cell: tuple[float, float],
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

    def shake_mouse(self, moves: int = 6, max_delta: int = 8) -> None:
        """Send short relative moves without clicking.

        Some RO clients ignore repeated ground clicks until the cursor nudges;
        call before retry clicks during navigation.
        """
        cap = max(1, max_delta)
        for _ in range(max(1, moves)):
            dx = random.randint(-cap, cap)
            dy = random.randint(-cap, cap)
            if dx == 0 and dy == 0:
                dx = random.choice((-1, 1))
            try:
                self._bridge.move_mouse(dx, dy)
            except Exception:
                logger.exception("shake_mouse move failed")
                return

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
        mob_cell: tuple[float, float],
        target_name: str | None = None,
        *,
        aim_settle_sec: float | None = None,
    ) -> None:
        """Move → optional settle → click.

        ``aim_settle_sec``: override profile settle for this click only;
        ``None`` uses the hunt engagement default. Pass ``0.0`` for ground
        walk clicks where delay must be minimal.
        """
        self.move(player_cell, mob_cell, target_name=target_name)
        settle = (
            self._aim_settle_sec if aim_settle_sec is None else aim_settle_sec
        )
        if settle > 0:
            time.sleep(settle)
        self.click()

    def _client_to_screen(self, client_xy: tuple[int, int]) -> tuple[int, int]:
        return (
            self._rect.left + client_xy[0],
            self._rect.top + client_xy[1],
        )

    def click_client_pixel(
        self,
        client_xy: tuple[int, int],
        *,
        settle_sec: float = 0.06,
    ) -> None:
        """Move to client-relative pixel and LMB click (HUD / inventory)."""
        target = self._client_to_screen(client_xy)
        cur = get_cursor_pos()
        self._bridge.move_mouse(target[0] - cur[0], target[1] - cur[1])
        if settle_sec > 0:
            time.sleep(settle_sec)
        self.click()

    def drag_map_cells(
        self,
        player_cell: tuple[int, int],
        from_cell: tuple[float, float],
        to_cell: tuple[float, float],
        *,
        segments: int = 16,
        settle_before_down_sec: float = 0.06,
        segment_pause_sec: float = 0.008,
    ) -> None:
        """LMB drag between two world cells (projection), same as client drag."""
        p0 = clamp_to_rect(
            self._projection.map_to_screen(player_cell, from_cell, self._rect),
            self._rect,
        )
        p1 = clamp_to_rect(
            self._projection.map_to_screen(player_cell, to_cell, self._rect),
            self._rect,
        )
        cur = get_cursor_pos()
        self._bridge.move_mouse(p0[0] - cur[0], p0[1] - cur[1])
        if settle_before_down_sec > 0:
            time.sleep(settle_before_down_sec)
        try:
            self._bridge.mouse_left_down()
            for i in range(1, segments + 1):
                t = i / segments
                xt = int(p0[0] + (p1[0] - p0[0]) * t)
                yt = int(p0[1] + (p1[1] - p0[1]) * t)
                cur = get_cursor_pos()
                self._bridge.move_mouse(xt - cur[0], yt - cur[1])
                if segment_pause_sec > 0:
                    time.sleep(segment_pause_sec)
        finally:
            try:
                self._bridge.mouse_left_up()
            except Exception:
                logger.exception("drag_map_cells: mouse_left_up")
        self._last_click_at = time.monotonic()

    def drag_client_pixels(
        self,
        from_client: tuple[int, int],
        to_client: tuple[int, int],
        *,
        segments: int = 14,
        settle_before_down_sec: float = 0.06,
        segment_pause_sec: float = 0.01,
    ) -> None:
        """LMB drag between two client-relative pixels (e.g. storage → inv)."""
        p0 = self._client_to_screen(from_client)
        p1 = self._client_to_screen(to_client)
        cur = get_cursor_pos()
        self._bridge.move_mouse(p0[0] - cur[0], p0[1] - cur[1])
        if settle_before_down_sec > 0:
            time.sleep(settle_before_down_sec)
        try:
            self._bridge.mouse_left_down()
            for i in range(1, segments + 1):
                t = i / segments
                xt = int(p0[0] + (p1[0] - p0[0]) * t)
                yt = int(p0[1] + (p1[1] - p0[1]) * t)
                cur = get_cursor_pos()
                self._bridge.move_mouse(xt - cur[0], yt - cur[1])
                if segment_pause_sec > 0:
                    time.sleep(segment_pause_sec)
        finally:
            try:
                self._bridge.mouse_left_up()
            except Exception:
                logger.exception("drag_client_pixels: mouse_left_up")
        self._last_click_at = time.monotonic()

    def shift_timestamps(self, delta: float) -> None:
        """Pause/resume support: slide ``last_click_at`` by ``delta``."""
        if self._last_click_at:
            self._last_click_at += delta
