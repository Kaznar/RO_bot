"""Aim + click façade on top of CameraProjection + HidBridge.

Translates a mob cell to a clamped screen pixel, sends a relative
mouse move to the HID bridge, settles, and emits a click. Tracks the
last click timestamp so callers can enforce re-click cooldowns.

All LMB/RMB actions go through dead-zone checks when a filter is set.
"""

from __future__ import annotations

import logging
import random
import time

from ro_bot.core.hid.bridge import HidBridge
from ro_bot.core.projection.camera import CameraProjection, clamp_to_rect
from ro_bot.core.window import WindowRect, get_cursor_pos
from ro_bot.hunt.config import AimOffsetSpec
from ro_bot.hunt.dead_zones.filter import DeadZoneFilter

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
        dead_zone_filter: DeadZoneFilter | None = None,
    ) -> None:
        self._bridge = bridge
        self._projection = projection
        self._rect = rect
        self._aim_settle_sec = aim_settle_sec
        self._dead_zone_filter = dead_zone_filter
        aim_map: dict[str, float] = {}
        for spec in aim_offsets:
            for n in spec.names:
                aim_map[n] = spec.y_offset_cells
        self._aim_offsets = aim_map
        self._last_click_at: float = 0.0

    def set_client_rect(self, rect: WindowRect) -> None:
        """Refresh client→screen mapping (e.g. after the game window moved)."""
        self._rect = rect

    def set_dead_zone_filter(self, dead_zone_filter: DeadZoneFilter | None) -> None:
        """Attach HUD dead-zone guard for all click/drag paths."""
        self._dead_zone_filter = dead_zone_filter

    def would_block_dead_zone(
        self,
        player_cell: tuple[int, int],
        target_cell: tuple[float, float],
        target_name: str | None = None,
    ) -> bool:
        """True when the projected click pixel would land in a dead zone."""
        if self._dead_zone_filter is None:
            return False
        y_offset = (
            self._aim_offsets.get(target_name, 0.0)
            if target_name is not None
            else 0.0
        )
        cell = (int(target_cell[0]), int(target_cell[1] + y_offset))
        return self._dead_zone_filter.contains(player_cell, cell)

    def _blocks_screen_px(self, px: int, py: int) -> bool:
        if self._dead_zone_filter is None:
            return False
        return self._dead_zone_filter.contains_screen_px(px, py)

    def _blocks_client_px(self, client_xy: tuple[int, int]) -> bool:
        if self._dead_zone_filter is None:
            return False
        return self._dead_zone_filter.contains_client_px(
            client_xy[0], client_xy[1],
        )

    def _blocks_screen_segment(
        self,
        p0: tuple[int, int],
        p1: tuple[int, int],
        *,
        samples: int = 16,
    ) -> bool:
        if self._dead_zone_filter is None:
            return False
        return self._dead_zone_filter.segment_intersects(
            p0, p1, samples=samples,
        )

    def _log_blocked(self, reason: str, **fields: object) -> None:
        parts = " ".join(f"{k}={v!r}" for k, v in fields.items())
        logger.info("Click blocked (dead zone): %s %s", reason, parts)

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
            # Ground / navigation (no mob name): RO often drops LMB if the last
            # HID event was also at this pixel — nudge cursor off, then aim.
            if target_name is None:
                self.shake_mouse(moves=2, max_delta=6)
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

    def click(self) -> bool:
        """Left-click at current cursor if not in a dead zone."""
        cur = get_cursor_pos()
        if self._blocks_screen_px(cur[0], cur[1]):
            self._log_blocked("cursor", px=cur)
            return False
        try:
            self._bridge.mouse_click()
            self._last_click_at = time.monotonic()
        except Exception:
            logger.exception("mouse_click failed")
            return False
        return True

    def click_right(self) -> bool:
        """Right-click at current cursor if not in a dead zone."""
        cur = get_cursor_pos()
        if self._blocks_screen_px(cur[0], cur[1]):
            self._log_blocked("cursor", px=cur)
            return False
        try:
            self._bridge.mouse_right_click()
            self._last_click_at = time.monotonic()
        except Exception:
            logger.exception("mouse_right_click failed")
            return False
        return True

    def aim_and_click(
        self,
        player_cell: tuple[int, int],
        mob_cell: tuple[float, float],
        target_name: str | None = None,
        *,
        aim_settle_sec: float | None = None,
        post_move_sleep_sec: float | None = None,
    ) -> bool:
        """Move → optional settle → click. Returns False if blocked by dead zone.

        ``aim_settle_sec``: override profile settle for this click only;
        ``None`` uses the hunt engagement default. ``0.0`` skips the pause;
        some game clients then ignore LMB right after ``MM`` (cursor not
        committed yet), so avoid ``0.0`` for ground navigation unless tested.

        ``post_move_sleep_sec``: extra sleep after ``aim_settle_sec`` and before
        ``click`` (HID / client pacing). Ground navigation can pass a small
        positive value (e.g. farm waypoints).
        """
        if self.would_block_dead_zone(player_cell, mob_cell, target_name):
            self._log_blocked(
                "projected",
                player=player_cell,
                target=mob_cell,
                name=target_name,
            )
            return False
        self.move(player_cell, mob_cell, target_name=target_name)
        settle = (
            self._aim_settle_sec if aim_settle_sec is None else aim_settle_sec
        )
        if settle > 0:
            time.sleep(settle)
        if post_move_sleep_sec is not None and post_move_sleep_sec > 0:
            time.sleep(post_move_sleep_sec)
        return self.click()

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
    ) -> bool:
        """Move to client-relative pixel and LMB click (HUD / inventory)."""
        if self._blocks_client_px(client_xy):
            self._log_blocked("client", xy=client_xy)
            return False
        target = self._client_to_screen(client_xy)
        cur = get_cursor_pos()
        self._bridge.move_mouse(target[0] - cur[0], target[1] - cur[1])
        if settle_sec > 0:
            time.sleep(settle_sec)
        return self.click()

    def drag_map_cells(
        self,
        player_cell: tuple[int, int],
        from_cell: tuple[float, float],
        to_cell: tuple[float, float],
        *,
        segments: int = 16,
        settle_before_down_sec: float = 0.06,
        segment_pause_sec: float = 0.008,
    ) -> bool:
        """LMB drag between two world cells (projection), same as client drag."""
        p0 = clamp_to_rect(
            self._projection.map_to_screen(player_cell, from_cell, self._rect),
            self._rect,
        )
        p1 = clamp_to_rect(
            self._projection.map_to_screen(player_cell, to_cell, self._rect),
            self._rect,
        )
        if self._blocks_screen_segment(p0, p1, samples=segments):
            self._log_blocked("map_drag", p0=p0, p1=p1)
            return False
        cur = get_cursor_pos()
        self._bridge.move_mouse(p0[0] - cur[0], p0[1] - cur[1])
        if settle_before_down_sec > 0:
            time.sleep(settle_before_down_sec)
        if self._blocks_screen_px(p0[0], p0[1]):
            self._log_blocked("map_drag_start", p0=p0)
            return False
        try:
            self._bridge.mouse_left_down()
            for i in range(1, segments + 1):
                t = i / segments
                xt = int(p0[0] + (p1[0] - p0[0]) * t)
                yt = int(p0[1] + (p1[1] - p0[1]) * t)
                if self._blocks_screen_px(xt, yt):
                    self._log_blocked("map_drag_path", px=(xt, yt))
                    return False
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
        return True

    def drag_client_pixels(
        self,
        from_client: tuple[int, int],
        to_client: tuple[int, int],
        *,
        segments: int = 14,
        settle_before_down_sec: float = 0.06,
        segment_pause_sec: float = 0.01,
    ) -> bool:
        """LMB drag between two client-relative pixels (e.g. storage → inv)."""
        if self._blocks_client_px(from_client) or self._blocks_client_px(to_client):
            self._log_blocked(
                "client_drag_endpoint",
                from_client=from_client,
                to_client=to_client,
            )
            return False
        p0 = self._client_to_screen(from_client)
        p1 = self._client_to_screen(to_client)
        if self._blocks_screen_segment(p0, p1, samples=segments):
            self._log_blocked("client_drag", p0=p0, p1=p1)
            return False
        cur = get_cursor_pos()
        self._bridge.move_mouse(p0[0] - cur[0], p0[1] - cur[1])
        if settle_before_down_sec > 0:
            time.sleep(settle_before_down_sec)
        if self._blocks_screen_px(p0[0], p0[1]):
            self._log_blocked("client_drag_start", p0=p0)
            return False
        try:
            self._bridge.mouse_left_down()
            for i in range(1, segments + 1):
                t = i / segments
                xt = int(p0[0] + (p1[0] - p0[0]) * t)
                yt = int(p0[1] + (p1[1] - p0[1]) * t)
                if self._blocks_screen_px(xt, yt):
                    self._log_blocked("client_drag_path", px=(xt, yt))
                    return False
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
        return True

    def shift_timestamps(self, delta: float) -> None:
        """Pause/resume support: slide ``last_click_at`` by ``delta``."""
        if self._last_click_at:
            self._last_click_at += delta
