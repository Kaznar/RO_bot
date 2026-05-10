"""Home → active farm map navigation via ordered map-cell waypoints.

Uses :class:`FarmHomeRouteConfig` nested under :class:`ReturnToFarmConfig`.
The controller calls :meth:`arm_from_town_arrival` on the same 0091 edge as
``home_prep`` (enter ``home_map`` from another map — butterfly wing / warp),
then this policy arms and issues aim-and-click steps along the waypoints.

When ``finish_on_active_farm_map`` is True (default), arriving on the farm
map with only farm-map waypoints left completes the route without walking to
the last anchor cell.

Portable across PCs: targets are RO cell coordinates, not screen pixels.

Stall handling uses **memory cell** idle time (not ``last_click_at``), so
``click_cooldown_sec=0`` still detects standing still. When the client lies
about walkability, small :meth:`AimService.shake_mouse` jitter runs before
repeat clicks and before stuck recovery.

After each map warp (0091) and when the route first arms, ground clicks wait
``post_map_change_grace_sec`` so the client can finish loading — no thread sleep.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ro_bot.core.memory.player_state import PlayerReader
from ro_bot.hunt.aim_service import AimService
from ro_bot.hunt.config import ReturnToFarmConfig

logger = logging.getLogger("ro_bot.hunt")

# Fraction of ``stuck_no_move_timeout_sec``: after this idle time, nudge the
# mouse before normal waypoint clicks (cheap client unblock).
_IDLE_SHAKE_FRACTION = 0.45


@dataclass
class _RouteState:
    index: int
    last_click_at: float | None = None
    stuck_attempts: int = 0
    last_seen_player_cell: tuple[int, int] | None = None
    player_cell_changed_at: float = 0.0
    last_recovery_at: float | None = None
    #: Monotonic deadline; no aim_and_click until ``now`` passes this.
    suppress_clicks_until: float | None = None


class FarmHomeRoutePolicy:
    """Tick-driven waypoint navigation from ``home_map`` to ``active_farm_map``."""

    def __init__(
        self,
        cfg: ReturnToFarmConfig,
        aim: AimService,
        player_reader: PlayerReader,
    ) -> None:
        hr = cfg.home_route
        if hr is None:
            raise ValueError("FarmHomeRoutePolicy requires ReturnToFarmConfig.home_route")
        self._rtf = cfg
        self._hr = hr
        self._aim = aim
        self._player_reader = player_reader
        self._state: _RouteState | None = None
        #: Set by the controller on the same 0091 edge as ``home_prep`` restock
        #: (enter ``home_map`` from a non-home map). Until then, do not arm the
        #: click path on a standing town login.
        self._navigation_armed: bool = False

    def arm_from_town_arrival(self) -> None:
        """Allow the town→farm waypoint sequence to start (after ``h`` / warp)."""
        if not self.enabled():
            return
        if self._navigation_armed:
            return
        self._navigation_armed = True
        logger.info("Farm home route: navigation armed (entered home_map)")

    def _disarm(self) -> None:
        self._state = None
        self._navigation_armed = False

    def enabled(self) -> bool:
        farm = (self._rtf.active_farm_map or "").strip()
        return (
            self._hr.enabled
            and bool(farm)
            and len(self._hr.waypoints) >= 2
        )

    def is_active(self) -> bool:
        return self._state is not None

    def should_automate_on_map(self, map_name: str) -> bool:
        """True while this map should not trigger manual-control suspension."""
        if not self.enabled():
            return False
        farm = self._rtf.active_farm_map
        assert farm is not None
        if map_name == farm:
            return False
        if self.is_active():
            return True
        return map_name == self._hr.home_map and self._navigation_armed

    def on_map_change(self, map_name: str, now: float) -> None:
        """Resync waypoint index after a warp (0091)."""
        if not self.enabled() or self._state is None:
            return
        self._sync_index(map_name)
        st = self._state
        if st is not None:
            st.last_seen_player_cell = None
            st.player_cell_changed_at = now
            st.last_recovery_at = None
            grace = max(0.0, self._hr.post_map_change_grace_sec)
            if grace > 0:
                st.suppress_clicks_until = now + grace

    def tick(
        self,
        now: float,
        current_map: str,
        *,
        suppress_navigation: bool = False,
    ) -> None:
        """Advance navigation. Safe every controller tick."""
        if not self.enabled():
            self._disarm()
            return

        farm = self._rtf.active_farm_map
        assert farm is not None
        farm_st = farm.strip()

        if self._state is None:
            if (
                self._navigation_armed
                and current_map == self._hr.home_map
                and current_map != farm_st
            ):
                grace = max(0.0, self._hr.post_map_change_grace_sec)
                sup = now + grace if grace > 0 else None
                self._state = _RouteState(index=0, suppress_clicks_until=sup)
                logger.info(
                    "Farm home route: armed (%d waypoints → '%s')",
                    len(self._hr.waypoints), farm_st,
                )
            return

        player = self._player_reader.read()
        if player.x == 0 and player.y == 0:
            return

        wps = self._hr.waypoints
        idx = self._state.index
        if idx >= len(wps):
            self._disarm()
            return

        self._sync_index(current_map)
        idx = self._state.index
        if idx >= len(wps):
            self._disarm()
            return

        if self._finish_on_farm_if_configured(current_map, farm_st, idx, wps):
            return

        wp = wps[idx]
        if current_map != wp.map_name:
            return

        pc = (player.x, player.y)
        st = self._state

        if st.last_seen_player_cell is None:
            st.last_seen_player_cell = pc
            st.player_cell_changed_at = now
        elif st.last_seen_player_cell != pc:
            st.last_seen_player_cell = pc
            st.player_cell_changed_at = now
            st.stuck_attempts = 0
            st.last_recovery_at = None

        if self._within_arrival(pc, (wp.x, wp.y)):
            st.index += 1
            st.last_seen_player_cell = pc
            st.player_cell_changed_at = now
            st.stuck_attempts = 0
            st.last_recovery_at = None
            logger.info(
                "Farm home route: reached waypoint %d/%d '%s' (%d,%d)",
                idx + 1, len(wps), wp.map_name, wp.x, wp.y,
            )
            if st.index >= len(wps):
                logger.info("Farm home route: completed")
                self._disarm()
            return

        grace = max(0.0, self._hr.post_map_change_grace_sec)
        if st.suppress_clicks_until is not None and now >= st.suppress_clicks_until:
            st.suppress_clicks_until = None
        nav_suppressed = suppress_navigation or (
            grace > 0
            and st.suppress_clicks_until is not None
            and now < st.suppress_clicks_until
        )

        stuck_after = max(0.05, self._hr.stuck_no_move_timeout_sec)
        idle_sec = now - st.player_cell_changed_at
        recovery_cooldown_ok = (
            st.last_recovery_at is None
            or now - st.last_recovery_at >= stuck_after
        )
        if (
            not nav_suppressed
            and idle_sec >= stuck_after
            and recovery_cooldown_ok
            and not self._within_arrival(pc, (wp.x, wp.y))
        ):
            if st.stuck_attempts >= self._hr.stuck_max_attempts_per_waypoint:
                logger.warning(
                    "Farm home route: no movement after clicks — "
                    "giving up waypoint %d/%d '%s' → disarming",
                    idx + 1, len(wps), wp.map_name,
                )
                self._disarm()
                return
            st.stuck_attempts += 1
            step_cell = self._recovery_step_cell(pc, (wp.x, wp.y), st.stuck_attempts)
            try:
                self._aim.shake_mouse()
                self._aim.aim_and_click(pc, step_cell, aim_settle_sec=0.0)
            except Exception:
                logger.exception("Farm home route: stuck recovery aim_and_click failed")
                return
            st.last_click_at = now
            st.last_recovery_at = now
            logger.info(
                "Farm home route: stuck recovery #%d wp %d/%d '%s' "
                "player=(%d,%d) step=(%d,%d) goal=(%d,%d)",
                st.stuck_attempts, idx + 1, len(wps), wp.map_name,
                pc[0], pc[1], step_cell[0], step_cell[1], wp.x, wp.y,
            )
            return

        if nav_suppressed:
            return

        last = st.last_click_at
        if last is not None and now - last < self._hr.click_cooldown_sec:
            return

        idle_shake_after = max(0.05, _IDLE_SHAKE_FRACTION * stuck_after)
        try:
            if idle_sec >= idle_shake_after:
                self._aim.shake_mouse()
            self._aim.aim_and_click(pc, (wp.x, wp.y), aim_settle_sec=0.0)
        except Exception:
            logger.exception("Farm home route: aim_and_click failed")
            return
        st.last_click_at = now
        logger.info(
            "Farm home route: click toward wp %d/%d '%s' target=(%d,%d) "
            "player=(%d,%d)",
            idx + 1, len(wps), wp.map_name, wp.x, wp.y, pc[0], pc[1],
        )

    @staticmethod
    def _recovery_step_cell(
        player: tuple[int, int],
        goal: tuple[int, int],
        variant: int,
    ) -> tuple[int, int]:
        """One orthogonal step toward ``goal`` (alternating axis by variant)."""
        px, py = player
        gx, gy = goal
        opts: list[tuple[int, int]] = []
        if gx > px:
            opts.append((px + 1, py))
        elif gx < px:
            opts.append((px - 1, py))
        if gy > py:
            opts.append((px, py + 1))
        elif gy < py:
            opts.append((px, py - 1))
        if not opts:
            return goal
        pick = (variant - 1) % len(opts)
        return opts[pick]

    def shift(self, delta: float) -> None:
        """Pause/resume: slide click timestamps."""
        st = self._state
        if st is None:
            return
        if st.last_click_at is not None:
            st.last_click_at += delta
        st.player_cell_changed_at += delta
        if st.last_recovery_at is not None:
            st.last_recovery_at += delta
        if st.suppress_clicks_until is not None:
            st.suppress_clicks_until += delta

    def _within_arrival(
        self,
        player_cell: tuple[int, int],
        target_cell: tuple[int, int],
    ) -> bool:
        r = max(0, self._hr.arrival_radius_cells)
        dx = abs(player_cell[0] - target_cell[0])
        dy = abs(player_cell[1] - target_cell[1])
        return max(dx, dy) <= r

    def _sync_index(self, map_name: str) -> None:
        assert self._state is not None
        wps = self._hr.waypoints
        i = self._state.index
        for j in range(i, len(wps)):
            if wps[j].map_name == map_name:
                if j != i:
                    logger.info(
                        "Farm home route: map sync '%s' → waypoint index %d",
                        map_name, j,
                    )
                self._state.index = j
                return
        for j in range(0, i):
            if wps[j].map_name == map_name:
                logger.info(
                    "Farm home route: map sync '%s' → waypoint index %d (rewind)",
                    map_name, j,
                )
                self._state.index = j
                return
        logger.warning(
            "Farm home route: map '%s' not in route — disarming",
            map_name,
        )
        self._disarm()

    def _finish_on_farm_if_configured(
        self,
        current_map: str,
        farm_st: str,
        idx: int,
        wps: tuple,
    ) -> bool:
        """Complete without walking to the last cell when configured."""
        if not self._hr.finish_on_active_farm_map:
            return False
        if current_map != farm_st:
            return False
        for j in range(idx, len(wps)):
            if wps[j].map_name != farm_st:
                return False
        logger.info(
            "Farm home route: completed (finish_on_active_farm_map; on %s)",
            farm_st,
        )
        self._disarm()
        return True
