"""Home → active farm map navigation via ordered map-cell waypoints.

Uses :class:`FarmHomeRouteConfig` nested under :class:`ReturnToFarmConfig`.
The controller calls :meth:`arm_from_town_arrival` on the same 0091 edge as
``home_prep`` (enter ``home_map`` from another map — butterfly wing / warp),
then this policy arms and issues aim-and-click steps along the waypoints.

When ``finish_on_active_farm_map`` is True (default), arriving on the farm
map with only farm-map waypoints left completes the route without walking to
the last anchor cell.

Portable across PCs: targets are RO map cells, not screen pixels.

On ``beach_dun3`` the scripted leg uses :mod:`beach_dun3_transit`: random
teleport ``t`` until the east corridor, then short ground clicks toward the
warp column (see that module for bounds).

Stall handling uses **memory cell** idle time (not ``last_click_at``), so
``click_cooldown_sec=0`` still detects standing still. Before each waypoint
click we ``shake_mouse`` and pass a short ``post_move_sleep_sec`` so the client
accepts LMB after ``MM``.

When the client lies about walkability, the same jitter runs again during
stuck recovery (plus a one-cell nudge click).

After each map warp (0091) and when the route first arms, ground clicks wait
``post_map_change_grace_sec`` so the client can finish loading — no thread sleep.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from ro_bot.core.hid.bridge import HidBridge
from ro_bot.core.memory.player_state import PlayerReader
from ro_bot.hunt.aim_service import AimService
from ro_bot.hunt.config import ReturnToFarmConfig
from ro_bot.hunt.routes.segments import beach_dun3_transit

logger = logging.getLogger("ro_bot.hunt")

# Ground navigation pacing — RO rejects LMB if MM and click are too tight.
_WAYPOINT_AIM_SETTLE_SEC = 0.15
_WAYPOINT_POST_MOVE_SEC = 0.10
# Even when plan sets ``click_cooldown_sec=0``, never spam faster than this.
_MIN_WAYPOINT_CLICK_COOLDOWN_SEC = 0.30
# Click a nearby cell toward the waypoint, not the full distant target (avoids
# clamp_to_rect edge clicks and “invalid location” on town geometry).
_MAX_WAYPOINT_STEP_CELLS = 4


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
    #: Last random teleport on ``beach_dun3`` while outside the east corridor.
    last_beach_teleport_at: float | None = None


class FarmHomeRoutePolicy:
    """Tick-driven waypoint navigation from ``home_map`` to ``active_farm_map``."""

    def __init__(
        self,
        cfg: ReturnToFarmConfig,
        aim: AimService,
        player_reader: PlayerReader,
        bridge: HidBridge,
        *,
        on_completed: Callable[[], None] | None = None,
    ) -> None:
        hr = cfg.home_route
        if hr is None:
            raise ValueError("FarmHomeRoutePolicy requires ReturnToFarmConfig.home_route")
        self._rtf = cfg
        self._hr = hr
        self._aim = aim
        self._player_reader = player_reader
        self._bridge = bridge
        self._on_completed = on_completed
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

    def _complete_route(self) -> None:
        if self._on_completed is not None:
            self._on_completed()
        self._disarm()

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

    def on_map_change(
        self,
        map_name: str,
        now: float,
        *,
        from_map: str | None = None,
    ) -> None:
        """Resync waypoint index after a warp (0091)."""
        if not self.enabled() or self._state is None:
            return
        self._sync_index(map_name)
        st = self._state
        if st is not None:
            st.last_seen_player_cell = None
            st.player_cell_changed_at = now
            st.last_recovery_at = None
            if beach_dun3_transit.is_wing_reposition_on_map(from_map, map_name):
                # Wing on beach_dun3 fires 0091 same→same; keep 0.4s ``t`` cadence.
                st.suppress_clicks_until = None
                logger.debug(
                    "Farm home route: beach_dun3 wing reposition — no post-map grace",
                )
                return
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

        grace = max(0.0, self._hr.post_map_change_grace_sec)
        if st.suppress_clicks_until is not None and now >= st.suppress_clicks_until:
            st.suppress_clicks_until = None
        nav_suppressed = suppress_navigation or (
            grace > 0
            and st.suppress_clicks_until is not None
            and now < st.suppress_clicks_until
        )

        if wp.map_name == "beach_dun3":
            self._tick_beach_dun3_transit(now, pc, st, wps, idx, nav_suppressed)
            return

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
                self._complete_route()
            return

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
                self._aim.aim_and_click(
                    pc,
                    step_cell,
                    aim_settle_sec=_WAYPOINT_AIM_SETTLE_SEC,
                    post_move_sleep_sec=_WAYPOINT_POST_MOVE_SEC,
                )
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

        if not self._click_cooldown_elapsed(now, st.last_click_at):
            return

        step_cell = self._step_toward_goal(
            pc, (wp.x, wp.y), _MAX_WAYPOINT_STEP_CELLS,
        )
        try:
            self._aim.shake_mouse()
            self._aim.aim_and_click(
                pc,
                step_cell,
                aim_settle_sec=_WAYPOINT_AIM_SETTLE_SEC,
                post_move_sleep_sec=_WAYPOINT_POST_MOVE_SEC,
            )
        except Exception:
            logger.exception("Farm home route: aim_and_click failed")
            return
        st.last_click_at = now
        logger.info(
            "Farm home route: click toward wp %d/%d '%s' step=(%d,%d) "
            "goal=(%d,%d) player=(%d,%d)",
            idx + 1, len(wps), wp.map_name,
            step_cell[0], step_cell[1], wp.x, wp.y, pc[0], pc[1],
        )

    def _tick_beach_dun3_transit(
        self,
        now: float,
        pc: tuple[int, int],
        st: _RouteState,
        wps: tuple,
        idx: int,
        nav_suppressed: bool,
    ) -> None:
        """Random ``t`` until corridor, then short clicks toward east exit."""
        px, py = pc
        if beach_dun3_transit.at_exit_zone(px, py):
            nxt = beach_dun3_transit.first_waypoint_index_after_map(
                wps, idx, "beach_dun3",
            )
            if nxt is None:
                logger.warning(
                    "Farm home route: beach_dun3 at exit but no following waypoint",
                )
                self._disarm()
                return
            st.index = nxt
            st.stuck_attempts = 0
            st.last_recovery_at = None
            st.last_beach_teleport_at = None
            ex, ey = beach_dun3_transit.exit_cell()
            logger.info(
                "Farm home route: beach_dun3 near exit (%d,%d) → waypoint index %d",
                ex, ey, nxt,
            )
            return

        if not beach_dun3_transit.in_corridor(px, py):
            if nav_suppressed:
                return
            cold = beach_dun3_transit.teleport_cooldown_sec()
            last_tp = st.last_beach_teleport_at
            if last_tp is None or now - last_tp >= cold:
                try:
                    self._bridge.press_key(beach_dun3_transit.teleport_key())
                except Exception:
                    logger.exception(
                        "Farm home route: beach_dun3 teleport key failed",
                    )
                    return
                st.last_beach_teleport_at = now
                logger.info(
                    "Farm home route: beach_dun3 player=(%d,%d) outside corridor "
                    "%r; pressed %r",
                    px,
                    py,
                    beach_dun3_transit.corridor_bounds(),
                    beach_dun3_transit.teleport_key(),
                )
            return

        stuck_after = max(0.05, self._hr.stuck_no_move_timeout_sec)
        idle_sec = now - st.player_cell_changed_at
        recovery_cooldown_ok = (
            st.last_recovery_at is None
            or now - st.last_recovery_at >= stuck_after
        )
        goal_cell = beach_dun3_transit.next_walk_cell(px, py)
        if (
            not nav_suppressed
            and idle_sec >= stuck_after
            and recovery_cooldown_ok
        ):
            if st.stuck_attempts >= self._hr.stuck_max_attempts_per_waypoint:
                logger.warning(
                    "Farm home route: beach_dun3 no progress → disarming",
                )
                self._disarm()
                return
            st.stuck_attempts += 1
            step_cell = self._recovery_step_cell(
                pc, goal_cell, st.stuck_attempts,
            )
            try:
                self._aim.shake_mouse()
                self._aim.aim_and_click(
                    pc,
                    step_cell,
                    aim_settle_sec=_WAYPOINT_AIM_SETTLE_SEC,
                    post_move_sleep_sec=_WAYPOINT_POST_MOVE_SEC,
                )
            except Exception:
                logger.exception(
                    "Farm home route: beach_dun3 stuck recovery failed",
                )
                return
            st.last_click_at = now
            st.last_recovery_at = now
            logger.info(
                "Farm home route: beach_dun3 stuck recovery #%d step=(%d,%d) "
                "goal=(%d,%d) player=(%d,%d)",
                st.stuck_attempts,
                step_cell[0],
                step_cell[1],
                goal_cell[0],
                goal_cell[1],
                px,
                py,
            )
            return

        if nav_suppressed:
            return

        if not self._click_cooldown_elapsed(now, st.last_click_at):
            return

        try:
            self._aim.shake_mouse()
            self._aim.aim_and_click(
                pc,
                goal_cell,
                aim_settle_sec=_WAYPOINT_AIM_SETTLE_SEC,
                post_move_sleep_sec=_WAYPOINT_POST_MOVE_SEC,
            )
        except Exception:
            logger.exception("Farm home route: beach_dun3 walk click failed")
            return
        st.last_click_at = now
        gx, gy = goal_cell
        logger.info(
            "Farm home route: beach_dun3 walk toward=(%d,%d) player=(%d,%d)",
            gx,
            gy,
            px,
            py,
        )

    def _click_cooldown_elapsed(
        self,
        now: float,
        last_click_at: float | None,
    ) -> bool:
        if last_click_at is None:
            return True
        need = max(
            self._hr.click_cooldown_sec,
            _MIN_WAYPOINT_CLICK_COOLDOWN_SEC,
        )
        return now - last_click_at >= need

    @staticmethod
    def _step_toward_goal(
        player: tuple[int, int],
        goal: tuple[int, int],
        max_step: int,
    ) -> tuple[int, int]:
        """Up to ``max_step`` cells per axis toward ``goal`` (keeps aim in FOV)."""
        px, py = player
        gx, gy = goal
        cap = max(1, max_step)
        dx = gx - px
        dy = gy - py
        if dx == 0 and dy == 0:
            return goal
        step_x = max(-cap, min(cap, dx))
        step_y = max(-cap, min(cap, dy))
        return (px + step_x, py + step_y)

    @staticmethod
    def _recovery_step_cell(
        player: tuple[int, int],
        goal: tuple[int, int],
        variant: int,
    ) -> tuple[int, int]:
        """One-cell offset cycling through orthogonal + diagonal nudges.

        Variant 1 is always the direct step toward ``goal`` so a single
        retry behaves the same as before. Subsequent variants add
        perpendicular sidesteps — critical when the goal lies on the same
        axis as the player (``dx == 0`` or ``dy == 0``), where the old
        single-option recovery just re-clicked the blocked cell forever
        (RO often reports "unwalkable" for a cell that's actually free
        only via a small detour).
        """
        px, py = player
        gx, gy = goal
        dx = gx - px
        dy = gy - py
        if dx == 0 and dy == 0:
            return goal
        sx = 1 if dx > 0 else (-1 if dx < 0 else 0)
        sy = 1 if dy > 0 else (-1 if dy < 0 else 0)
        if sx != 0 and sy != 0:
            opts: tuple[tuple[int, int], ...] = (
                (px + sx, py),
                (px, py + sy),
                (px + sx, py + sy),
                (px + sx, py - sy),
                (px - sx, py + sy),
            )
        elif sy != 0:
            opts = (
                (px, py + sy),
                (px + 1, py + sy),
                (px - 1, py + sy),
                (px + 1, py),
                (px - 1, py),
            )
        else:
            opts = (
                (px + sx, py),
                (px + sx, py + 1),
                (px + sx, py - 1),
                (px, py + 1),
                (px, py - 1),
            )
        return opts[(variant - 1) % len(opts)]

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
        if st.last_beach_teleport_at is not None:
            st.last_beach_teleport_at += delta

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
        self._complete_route()
        return True
