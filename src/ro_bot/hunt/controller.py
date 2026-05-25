"""Hunt controller — thin orchestrator over the policy modules.

Responsibilities (ordered per tick):

  1. Skip entire tick if paused.
  2. Let heal & buff policies check HP / intervals.
  3. Drain sniffer events (died / lost / map_reset).
  4. On map_reset → reset target + blacklist + observers.
  5. Expire stale blacklist entries.
  6. Refresh :class:`CellObserver` from the tracker.
  7. Danger check — teleport and abort if any dangerous mob is in view.
  8. If engaged: resolve kill / loss / timeout, else continue engagement.
  9. Otherwise: collect candidates, pick nearest, engage — or fire idle
     action after the configured grace.

  Overweight (memory): if weight / max ≥ ratio, suspend steps 8–9,
  press the overweight key (e.g. storage macro), do not idle-teleport.

  Warp return: hunt map → manual-control map → back to that hunt map
  queues one idle teleport before step 9 (needs ``idle_action``).

  Death return (optional): when memory HP crosses into ``(0, hp_at_most]`` on
  a hunt map, one ground walk click ``delta_*_cells`` from the player (town
  warp); arrival on ``manual_control_maps`` matches manual ``h`` hand-off.

  Active farm: when ``return_to_farm.active_farm_map`` is set, a 0091
  edge from a configured **neighbor** of that farm onto the farm map
  also queues one idle teleport first (return-to-farm walk-off warp).

Everything heavy lives in submodules (policies / state containers).
This file is the glue.
"""

from __future__ import annotations

import dataclasses
import logging
import time
from collections.abc import Callable

from ro_bot.core.hid.bridge import HidBridge
from ro_bot.core.memory.player_state import PlayerReader, PlayerState
from ro_bot.core.window import get_client_rect
from ro_bot.core.network.packets import VanishType
from ro_bot.core.network.sniffer import PacketSniffer
from ro_bot.core.tracking.entity_tracker import EntityTracker
from ro_bot.hunt.aim_service import AimService
from ro_bot.hunt.blacklist import Blacklist
from ro_bot.hunt.cell_observer import CellObserver
from ro_bot.hunt.config import HuntConfig
from ro_bot.hunt.constants import (
    ENGAGED_POLL_SEC,
    IDLE_POLL_SEC,
    NAVIGATION_POLL_SEC,
    NO_CANDIDATE_LOG_INTERVAL_SEC,
    WEIGHT_SNAPSHOT_INTERVAL_SEC,
)
from ro_bot.hunt.dead_zones.filter import DeadZoneFilter
from ro_bot.hunt.event_bus import EventBus
from ro_bot.hunt.pause import PauseToken
from ro_bot.hunt.policies.buffs import BuffPolicy
from ro_bot.hunt.policies.death_return import DeathReturnPolicy
from ro_bot.hunt.policies.engagement import EngagementMachine, TargetState
from ro_bot.hunt.policies.escape import EscapePolicy
from ro_bot.hunt.policies.heal import HealPolicy
from ro_bot.hunt.policies.idle_action import IdleActionPolicy
from ro_bot.hunt.policies.overweight import OverweightPolicy
from ro_bot.hunt.policies.approach_stall import ApproachStallPolicy
from ro_bot.hunt.policies.automation_stall import (
    AutomationStallGuard,
    automation_stall_limit_sec,
    recover_automation_stall,
)
from ro_bot.hunt.policies.path_stuck import PathStuckPolicy
from ro_bot.hunt.policies.player_closer import PlayerCloserPolicy
from ro_bot.hunt.policies.remote_contested import RemoteContestedPolicy
from ro_bot.hunt.policies.farm_home_route import FarmHomeRoutePolicy
from ro_bot.hunt.policies.farm_arrival import FarmArrivalPolicy
from ro_bot.hunt.policies.home_prep import HomePrepPolicy
from ro_bot.hunt.policies.return_to_farm import ReturnToFarmPolicy
from ro_bot.hunt.policies.stack_cell import (
    pick_candidate,
    player_near_cell,
    should_defer_warp_near_stack,
)
from ro_bot.hunt.policies.targeting import collect_candidates

logger = logging.getLogger("ro_bot.hunt")


class HuntController:
    """Tick-driven state machine for single-target LMB hunting."""

    def __init__(
        self,
        *,
        cfg: HuntConfig,
        bridge: HidBridge,
        sniffer: PacketSniffer,
        tracker: EntityTracker,
        player_reader: PlayerReader,
        aim: AimService,
        dead_zone_filter: DeadZoneFilter,
        game_hwnd: int | None = None,
    ) -> None:
        self._cfg = cfg
        self._bridge = bridge
        self._sniffer = sniffer
        self._tracker = tracker
        self._player_reader = player_reader
        self._game_hwnd = game_hwnd
        self._aim = aim

        self._events = EventBus()
        self._cells = CellObserver(cfg.engagement.target_settle_sec)
        self._blacklist = Blacklist()
        self._pause = PauseToken()

        self._engagement = EngagementMachine(
            aim=aim,
            cell_observer=self._cells,
            dead_zone_filter=dead_zone_filter,
            reaim_cooldown_sec=cfg.engagement.reaim_click_cooldown_sec,
            bridge=bridge,
            reaim_hold_dist=cfg.engagement.reaim_hold_dist,
            engage_skill_key=cfg.engagement.engage_skill_key,
            engage_skill_delay_sec=cfg.engagement.engage_skill_delay_sec,
            engage_skill_repeat_sec=cfg.engagement.engage_skill_repeat_sec,
        )
        self._path_stuck = PathStuckPolicy(cfg.engagement, self._blacklist)
        self._approach_stall = ApproachStallPolicy(cfg.engagement, self._blacklist)
        self._remote_contested = RemoteContestedPolicy(cfg.engagement, self._blacklist)
        self._player_closer = PlayerCloserPolicy(
            cfg.engagement,
            self._blacklist,
            sniffer,
            allowed_names=cfg.allowed_names,
            dangerous_names=cfg.dangerous_names,
            char_name=cfg.char_name,
        )

        self._heal = (
            HealPolicy(
                cfg.heal,
                bridge,
                sniffer,
                cfg.manual_control_maps,
                all_maps=cfg.ignore_map_restrictions,
            )
            if cfg.heal is not None else None
        )
        self._death_return = (
            DeathReturnPolicy(
                cfg.death_return,
                bridge,
                aim,
                sniffer,
                cfg.manual_control_maps,
                all_maps=cfg.ignore_map_restrictions,
            )
            if cfg.death_return is not None
            else None
        )
        self._buffs = BuffPolicy(
            cfg.buffs,
            bridge,
            sniffer,
            cfg.manual_control_maps,
            all_maps=cfg.ignore_map_restrictions,
        )
        self._idle = (
            IdleActionPolicy(cfg.idle_action, bridge)
            if cfg.idle_action is not None else None
        )
        self._stall_guard = AutomationStallGuard(automation_stall_limit_sec(cfg))
        self._overweight = (
            OverweightPolicy(cfg.overweight, bridge)
            if cfg.overweight is not None else None
        )
        self._escape = (
            EscapePolicy(cfg.escape, cfg.dangerous_names, bridge, sniffer)
            if cfg.escape is not None else None
        )
        self._return_to_farm = (
            ReturnToFarmPolicy(cfg.return_to_farm, aim, player_reader)
            if cfg.return_to_farm is not None
            and cfg.return_to_farm.transitions
            else None
        )
        self._farm_arrival = HuntController._make_farm_arrival_policy(
            cfg,
            bridge,
            on_key_pressed=self._buffs.mark_pressed,
        )
        on_route_completed = (
            self._farm_arrival.arm
            if self._farm_arrival is not None
            else None
        )
        self._farm_home_route = self._make_farm_home_route_policy(
            cfg, aim, player_reader, bridge, on_completed=on_route_completed,
        )
        self._home_prep = HuntController.make_home_prep_policy(
            cfg, bridge, player_reader, aim, game_hwnd=self._game_hwnd,
        )

        self._dead_zone_filter = dead_zone_filter

        self._installed = False
        self._kills = 0
        self._timeouts = 0
        self._last_no_candidate_log: float = 0.0
        self._last_weight_log: float = 0.0
        # Set by path-stuck abandonment; consumed once by the next
        # candidate-selection pass to bypass idle grace when nothing
        # else is reachable.
        self._immediate_teleport_pending: bool = False
        # When only dead-zone-blocked mobs are visible, give them a short
        # grace window to walk out, then allow idle teleport anyway.
        self._dead_zone_blocked_since: float | None = None
        # When every visible whitelisted mob is in the blacklist (i.e. the
        # only candidate just timed out and is in cooldown), force idle TP
        # after ``engagement.all_blacklisted_force_tp_sec`` so we don't loop
        # forever on the same unreachable target.
        self._all_blacklisted_since: float | None = None
        #: After idle TP on a hunt map, re-teleport while other players
        #: remain visible until this monotonic deadline.
        self._post_tp_player_check_until: float | None = None
        # Active while on a map from manual_control_maps.
        # In this mode the hunt loop behaves like pause: no attack, no TP,
        # no policy actions. Player controls movement manually.
        self._manual_control_map: str | None = None
        self._was_overweight_last_tick: bool = False
        self._warp_return_tp_pending: bool = False
        self._warp_return_tp_target: str | None = None
        self._pending_warp_return_idle_tp: bool = False
        #: Log line for :meth:`IdleActionPolicy.force_fire` when
        #: ``_pending_warp_return_idle_tp`` is set.
        self._pending_warp_return_idle_reason: str | None = None
        #: Previous ``map_name`` from the last sniffer map callback (0091).
        self._map_change_listener_prev: str | None = None
        self._stack_preferred_gid: int | None = None
        self._stack_preferred_cell: tuple[int, int] | None = None
        self._stack_preferred_until: float = 0.0
        self._stack_cell_abandon_counts: dict[tuple[int, int], int] = {}

    @staticmethod
    def _make_farm_arrival_policy(
        cfg: HuntConfig,
        bridge: HidBridge,
        *,
        on_key_pressed: Callable[[str, float], None] | None = None,
    ) -> FarmArrivalPolicy | None:
        rtf = cfg.return_to_farm
        if rtf is None or not rtf.farm_arrival_steps:
            return None
        farm = (rtf.active_farm_map or "").strip()
        if not farm:
            return None
        return FarmArrivalPolicy(
            rtf.farm_arrival_steps,
            bridge,
            farm,
            on_key_pressed=on_key_pressed,
        )

    @staticmethod
    def _make_farm_home_route_policy(
        cfg: HuntConfig,
        aim: AimService,
        player_reader: PlayerReader,
        bridge: HidBridge,
        *,
        on_completed: Callable[[], None] | None = None,
    ) -> FarmHomeRoutePolicy | None:
        rtf = cfg.return_to_farm
        if rtf is None or rtf.home_route is None:
            return None
        hr = rtf.home_route
        farm = (rtf.active_farm_map or "").strip()
        if not hr.enabled or len(hr.waypoints) < 2 or not farm:
            return None
        return FarmHomeRoutePolicy(
            rtf, aim, player_reader, bridge, on_completed=on_completed,
        )

    @staticmethod
    def make_home_prep_policy(
        cfg: HuntConfig,
        bridge: HidBridge,
        player_reader: PlayerReader,
        aim: AimService,
        *,
        force_enabled: bool = False,
        game_hwnd: int | None = None,
    ) -> HomePrepPolicy | None:
        rtf = cfg.return_to_farm
        if rtf is None or rtf.home_route is None:
            return None
        hp = rtf.home_prep
        if hp is None or not hp.steps:
            return None
        if not hp.enabled and not force_enabled:
            return None
        if force_enabled and not hp.enabled:
            hp_on = dataclasses.replace(hp, enabled=True)
            rtf = dataclasses.replace(rtf, home_prep=hp_on)
        return HomePrepPolicy(
            rtf, bridge, player_reader, aim, game_hwnd=game_hwnd,
        )

    # ── Lifecycle ───────────────────────────────────────────────────

    def install(self) -> None:
        """Subscribe to sniffer events. Call once before ticking."""
        if self._installed:
            return
        self._sniffer.add_entity_vanish_listener(self._on_vanish)
        self._sniffer.add_map_change_listener(self._on_map_change)
        self._buffs.install()
        self._stall_guard.reset(time.monotonic())
        self._installed = True
        logger.info(
            "HuntController installed: char='%s' allowed=%s manual_control_maps=%s "
            "target_all_mobs=%s ignore_map_restrictions=%s "
            "timeout=%.1fs blacklist=%.0fs dead_zones=%d",
            self._cfg.char_name,
            sorted(self._cfg.allowed_names),
            sorted(self._cfg.manual_control_maps),
            self._cfg.target_all_mobs,
            self._cfg.ignore_map_restrictions,
            self._cfg.engagement.kill_timeout_sec,
            self._cfg.engagement.blacklist_sec,
            len(self._cfg.dead_zones),
        )
        if self._cfg.overweight is not None:
            ow = self._cfg.overweight
            logger.info(
                "Overweight policy: ratio=%.2f key='%s' interval=%.1fs",
                ow.ratio, ow.key, ow.press_interval_sec,
            )

    def uninstall(self) -> None:
        if not self._installed:
            return
        self._sniffer.remove_entity_vanish_listener(self._on_vanish)
        self._sniffer.remove_map_change_listener(self._on_map_change)
        self._buffs.uninstall()
        self._installed = False
        self._engagement.state.clear()
        self._cells.clear()
        self._blacklist.clear()
        self._map_change_listener_prev = None
        logger.info(
            "HuntController uninstalled (kills=%d timeouts=%d)",
            self._kills, self._timeouts,
        )

    # ── Pause / resume ──────────────────────────────────────────────

    def is_paused(self) -> bool:
        return self._pause.is_paused

    def pause(self) -> None:
        if self._pause.is_paused:
            return
        self._pause.pause()
        logger.info("Paused")

    def resume(self) -> None:
        if not self._pause.is_paused:
            return
        delta = self._pause.resume()
        self._engagement.shift(delta)
        self._cells.shift(delta)
        self._blacklist.shift(delta)
        if self._heal is not None:
            self._heal.shift(delta)
        self._buffs.shift(delta)
        if self._idle is not None:
            self._idle.shift(delta)
        if self._escape is not None:
            self._escape.shift(delta)
        if self._return_to_farm is not None:
            self._return_to_farm.shift(delta)
        if self._farm_home_route is not None:
            self._farm_home_route.shift(delta)
        if self._farm_arrival is not None:
            self._farm_arrival.shift(delta)
        if self._home_prep is not None:
            self._home_prep.shift(delta)
        if self._overweight is not None:
            self._overweight.shift(delta)
        if self._last_no_candidate_log:
            self._last_no_candidate_log += delta
        if self._last_weight_log:
            self._last_weight_log += delta
        if self._dead_zone_blocked_since is not None:
            self._dead_zone_blocked_since += delta
        if self._all_blacklisted_since is not None:
            self._all_blacklisted_since += delta
        if self._post_tp_player_check_until is not None:
            self._post_tp_player_check_until += delta
        self._stall_guard.shift(delta)
        logger.info("Resumed after %.1fs paused", delta)

    # ── Tick interval ───────────────────────────────────────────────

    def tick_interval_sec(self) -> float:
        if self._pause.is_paused:
            return IDLE_POLL_SEC
        current_map = self._sniffer.get_map_name() or "?"
        if (
            self._home_prep is not None
            and self._home_prep.suppress_farm_home_route_navigation(current_map)
        ):
            return NAVIGATION_POLL_SEC
        if (
            self._farm_home_route is not None
            and self._farm_home_route.is_active()
        ):
            return NAVIGATION_POLL_SEC
        if (
            self._farm_arrival is not None
            and self._farm_arrival.is_active()
        ):
            return NAVIGATION_POLL_SEC
        return (
            ENGAGED_POLL_SEC
            if self._engagement.state.gid is not None
            else IDLE_POLL_SEC
        )

    # ── Main tick ───────────────────────────────────────────────────

    def tick(self) -> None:
        if self._pause.is_paused:
            return

        now = time.monotonic()
        self._tick_body(now)

    def _tick_body(self, now: float) -> None:
        events = self._events.drain()
        if events.map_reset:
            self._handle_map_reset(events.map_change_pairs)
            return

        current_map = self._sniffer.get_map_name() or "?"
        st_mem = self._read_player_state()
        survival = self._suppress_automation_for_death_return_survival(st_mem)

        if self._pending_warp_return_idle_tp:
            if survival:
                self._pending_warp_return_idle_tp = False
                self._pending_warp_return_idle_reason = None
            elif self._is_manual_control_map(current_map):
                self._pending_warp_return_idle_tp = False
                self._pending_warp_return_idle_reason = None
            elif self._idle is not None:
                if self._idle.force_fire(
                    now,
                    self._pending_warp_return_idle_reason
                    or "warp escape before hunt",
                ):
                    self._stall_guard.mark_progress(now)
                self._pending_warp_return_idle_tp = False
                self._pending_warp_return_idle_reason = None
                return
            else:
                logger.warning(
                    "warp-return teleport skipped (no profile.idle_action)",
                )
                self._pending_warp_return_idle_tp = False
                self._pending_warp_return_idle_reason = None
                return

        route_automates = (
            self._farm_home_route is not None
            and self._farm_home_route.should_automate_on_map(current_map)
        )
        rtf_active = (
            self._return_to_farm is not None
            and self._return_to_farm.is_active()
        )
        if (
            self._is_manual_control_map(current_map)
            and not route_automates
            and not rtf_active
        ):
            self._enter_manual_control_mode(current_map)
            return
        self._leave_manual_control_mode(current_map)

        st_dr = st_mem
        if self._death_return is not None:
            if self._death_return.tick(current_map, st_dr, now):
                if self._engagement.state.gid is not None:
                    self._engagement.state.clear()
                if self._idle is not None:
                    self._idle.on_map_reset()
                return

        self._maybe_log_weight_snapshot(now)

        if not survival and self._heal is not None:
            self._heal.tick(now)

        self._blacklist.expire(now)

        visible = self._tracker.get_all_positions()
        self._cells.update(visible, now)

        if (
            not survival
            and self._escape is not None
            and self._escape.press_if_ready(now)
        ):
            self._handle_escape_tick()
            return

        # Town restock + home→farm waypoint navigation must run even while
        # ``survival`` is true (HP in the death_return band on sniffer/memory).
        # Otherwise ``if survival: return`` below skips :class:`HomePrepPolicy`
        # entirely and restock never starts on ``home_map``.
        prep_suppress = False
        if self._home_prep is not None:
            self._home_prep.tick(now, current_map)
            prep_suppress = self._home_prep.suppress_farm_home_route_navigation(
                current_map,
            )

        if self._farm_home_route is not None:
            self._farm_home_route.tick(
                now, current_map, suppress_navigation=prep_suppress,
            )
            if self._farm_home_route.is_active():
                if self._engagement.state.gid is not None:
                    self._engagement.state.clear()
                return

        if self._farm_arrival is not None:
            self._farm_arrival.tick(now, current_map)
            if self._farm_arrival.is_active():
                if self._engagement.state.gid is not None:
                    self._engagement.state.clear()
                return

        if not survival:
            self._buffs.tick(now)

        if survival:
            return

        if self._return_to_farm is not None and self._return_to_farm.is_active():
            if self._engagement.state.gid is not None:
                # We may have engaged something on the farm map just
                # before walking through the warp. Drop it — that GID
                # isn't on this map anyway.
                self._engagement.state.clear()
            self._return_to_farm.tick(now)
            return

        st_ov = self._read_player_state()
        overloaded = (
            self._overweight is not None
            and st_ov is not None
            and self._overweight.is_overloaded(st_ov)
        )
        if overloaded:
            if self._engagement.state.gid is not None:
                logger.info(
                    "Overweight: clearing target gid=%d (%.1f%% of max weight)",
                    self._engagement.state.gid,
                    100.0 * st_ov.weight / st_ov.weight_max,
                )
                self._engagement.state.clear()
            self._overweight.tick(now)
            if not self._was_overweight_last_tick and self._idle is not None:
                self._idle.on_map_reset()
            self._stall_guard.mark_progress(now)
            self._was_overweight_last_tick = True
            return
        self._was_overweight_last_tick = False

        if self._engagement.state.gid is not None:
            if self._resolve_engaged(now, events.died_gids, events.lost_gids):
                return
            # Fell through: target was killed/lost/timed-out. Continue
            # into candidate selection with a fresh slate.

        player_cell = self._read_player_cell()
        if player_cell is None:
            if self._maybe_recover_automation_stall(now, current_map):
                player_cell = self._read_player_cell()
            if player_cell is None:
                return

        if self._maybe_retp_if_players_visible(now, current_map):
            return

        if self._maybe_defer_hunt_for_players(now, player_cell, current_map):
            return

        self._select_and_engage(visible, player_cell, now)
        self._maybe_recover_automation_stall(now, current_map)

    # ── Helpers ─────────────────────────────────────────────────────

    def _handle_map_reset(
        self,
        pairs: tuple[tuple[str | None, str], ...],
    ) -> None:
        for old_map, new_map in pairs:
            self._apply_warp_return_transition(old_map, new_map)
        self._maybe_arm_town_return_flow(pairs)

        map_name = self._sniffer.get_map_name() or "?"

        mode = (
            "manual-control"
            if self._is_manual_control_map(map_name)
            else "active-hunt"
        )
        logger.info("Map change → %s (%s) → reset hunt state", map_name, mode)
        self._engagement.state.clear()
        self._blacklist.clear()
        self._cells.clear()
        self._immediate_teleport_pending = False
        self._dead_zone_blocked_since = None
        self._all_blacklisted_since = None
        if self._idle is not None:
            self._idle.on_map_reset()
        self._clear_stack_state()
        self._stall_guard.reset(time.monotonic())
        if self._death_return is not None:
            self._death_return.on_map_reset()
        self._player_closer.on_map_reset()
        from_map: str | None = None
        for old_map, new_map in pairs:
            if new_map == map_name:
                from_map = old_map
        if self._farm_home_route is not None:
            self._farm_home_route.on_map_change(
                map_name, time.monotonic(), from_map=from_map,
            )
        if self._return_to_farm is not None:
            if (
                self._farm_home_route is not None
                and self._farm_home_route.is_active()
            ):
                self._return_to_farm.disarm()
            else:
                self._return_to_farm.on_map_change(map_name, time.monotonic())
        if self._overweight is not None:
            self._overweight.on_map_reset()
        self._refresh_client_rect_from_window()
        if (
            mode == "active-hunt"
            and self._cfg.engagement.player_visible_retp_sec > 0
        ):
            for old_map, new_map in pairs:
                if old_map and old_map == new_map:
                    self._post_tp_player_check_until = time.monotonic()
                    break

    def _maybe_retp_if_players_visible(
        self,
        now: float,
        current_map: str,
    ) -> bool:
        """Re-teleport after idle TP while other players remain visible."""
        if self._post_tp_player_check_until is None:
            return False
        if (
            self._cfg.engagement.player_visible_retp_sec <= 0
            or not self._player_closer.enabled
            or self._idle is None
            or self._is_manual_control_map(current_map)
        ):
            self._post_tp_player_check_until = None
            return False
        others = self._player_closer.visible_other_players()
        if not others:
            self._post_tp_player_check_until = None
            return False
        labels = ", ".join(
            f"{name}@({x},{y})" for _, name, x, y in others[:3]
        )
        if len(others) > 3:
            labels += f", +{len(others) - 3} more"
        if not self._idle.force_fire(
            now,
            f"player(s) visible after teleport ({labels})",
        ):
            return False
        logger.warning(
            "Re-teleport: %d other player(s) visible after idle TP on %s",
            len(others), current_map,
        )
        self._stall_guard.mark_progress(now)
        return True

    def _maybe_defer_hunt_for_players(
        self,
        now: float,
        player_cell: tuple[int, int],
        current_map: str,
    ) -> bool:
        """KS priority: no new engages while other players are visible."""
        deferred, reason = self._player_closer.hunt_deferred(player_cell)
        if not deferred:
            return False
        if self._idle is None:
            logger.info("KS prio: deferring hunt — %s (no idle_action)", reason)
            return True
        if self._idle.force_fire(now, f"KS prio — {reason}"):
            logger.warning("KS prio: deferring hunt — %s", reason)
            self._stall_guard.mark_progress(now)
        return True

    def _refresh_client_rect_from_window(self) -> None:
        """Re-read client area so HUD ``click_client`` stays aligned if the window moved."""
        if self._game_hwnd is None:
            return
        rect = get_client_rect(self._game_hwnd)
        self._aim.set_client_rect(rect)
        self._dead_zone_filter = dataclasses.replace(
            self._dead_zone_filter, rect=rect,
        )
        self._aim.set_dead_zone_filter(self._dead_zone_filter)

    def arm_farm_home_route_after_manual_town_prep(self) -> None:
        """Standalone ``home-prep``: same arming as a 0091 town entry (no sniffer pair)."""
        if self._farm_home_route is not None:
            self._farm_home_route.arm_from_town_arrival()

    def _maybe_arm_town_return_flow(
        self,
        pairs: tuple[tuple[str | None, str], ...],
    ) -> None:
        """Arm town restock and farm-home navigation after ``home_map`` entry."""
        rtf = self._cfg.return_to_farm
        if rtf is None or rtf.home_route is None:
            return
        hm = (rtf.home_route.home_map or "").strip()
        if not hm:
            return
        for old_map, new_map in pairs:
            if (
                self._return_to_farm is not None
                and self._return_to_farm.is_configured_neighbor(new_map)
            ):
                logger.info(
                    "Map change %s → %s: skip town prep/home route "
                    "(configured active-farm neighbor walk-back)",
                    old_map, new_map,
                )
                continue
            if (
                new_map == hm
                and old_map is not None
                and old_map not in ("?", "")
                and old_map != new_map
                and old_map != hm
            ):
                if self._home_prep is not None:
                    self._home_prep.arm_restock()
                if self._farm_home_route is not None:
                    self._farm_home_route.arm_from_town_arrival()

    def _should_skip_warp_escape_idle_tp(self, map_name: str) -> bool:
        """True when ``home_route`` waypoints already cover this map.

        Returning from ``manual_control_maps`` (e.g. Comodo) onto a transit
        dungeon that is part of the scripted walk (``beach_dun3``) must not
        fire ``idle_action`` — it breaks :class:`FarmHomeRoutePolicy` clicks.
        """
        rtf = self._cfg.return_to_farm
        if rtf is None:
            return False
        hr = rtf.home_route
        if hr is None or not hr.enabled:
            return False
        return any(wp.map_name == map_name for wp in hr.waypoints)

    def _apply_warp_return_transition(
        self,
        old_map: str | None,
        new_map: str,
    ) -> None:
        """Detect hunt↔town hops for one 0x0091 edge (sniffer-thread order)."""
        if new_map == "?":
            return

        if (
            self._warp_return_tp_pending
            and self._warp_return_tp_target is not None
            and new_map == self._warp_return_tp_target
            and old_map is not None
            and old_map != "?"
            and old_map != new_map
        ):
            self._warp_return_tp_pending = False
            self._warp_return_tp_target = None
            if self._should_skip_warp_escape_idle_tp(new_map):
                logger.info(
                    "Map change %s → %s: skip idle teleport "
                    "(home_route covers '%s'; no warp escape)",
                    old_map, new_map, new_map,
                )
            else:
                self._pending_warp_return_idle_tp = True
                self._pending_warp_return_idle_reason = (
                    "return from manual-control map — warp escape"
                )
                logger.info(
                    "Map change %s → %s: queued idle teleport before hunt "
                    "(return from manual-control map)",
                    old_map, new_map,
                )

        if (
            old_map is not None
            and old_map != "?"
            and old_map != new_map
            and old_map not in self._cfg.manual_control_maps
            and self._is_manual_control_map(new_map)
        ):
            self._warp_return_tp_pending = True
            self._warp_return_tp_target = old_map
            logger.info(
                "Left hunt map '%s' for manual-control '%s' — "
                "will idle-teleport once on return to farm",
                old_map, new_map,
            )

        self._maybe_queue_idle_tp_on_active_farm_return(old_map, new_map)

    def _maybe_queue_idle_tp_on_active_farm_return(
        self,
        old_map: str | None,
        new_map: str,
    ) -> None:
        """After walking from a configured neighbor onto ``active_farm_map``."""
        rtf = self._cfg.return_to_farm
        if rtf is None or not rtf.transitions:
            return
        active = (rtf.active_farm_map or "").strip()
        if not active or new_map != active:
            return
        if old_map is None or old_map in ("", "?"):
            return
        if old_map == new_map:
            return
        for t in rtf.transitions:
            if t.farm_map == active and t.neighbor_map == old_map:
                self._pending_warp_return_idle_tp = True
                self._pending_warp_return_idle_reason = (
                    f"return to active_farm_map '{active}' from neighbor "
                    f"'{old_map}' — warp escape"
                )
                logger.info(
                    "Map change %s → %s: queued idle teleport before hunt "
                    "(neighbor warp → active_farm_map)",
                    old_map, new_map,
                )
                return

    def _is_manual_control_map(self, map_name: str) -> bool:
        if map_name == "?":
            return False
        return map_name in self._cfg.manual_control_maps

    def _enter_manual_control_mode(self, map_name: str) -> None:
        if self._manual_control_map == map_name:
            return
        self._manual_control_map = map_name
        if self._engagement.state.gid is not None:
            self._engagement.state.clear()
        self._immediate_teleport_pending = False
        self._dead_zone_blocked_since = None
        self._all_blacklisted_since = None
        if self._idle is not None:
            # Re-entering combat maps starts with a fresh idle window.
            self._idle.on_map_reset()
        logger.info(
            "Manual-control map '%s': automation suspended "
            "(no attack, no teleport)",
            map_name,
        )

    def _leave_manual_control_mode(self, map_name: str) -> None:
        if self._manual_control_map is None:
            return
        prev = self._manual_control_map
        self._manual_control_map = None
        logger.info(
            "Left manual-control map '%s' -> '%s': automation resumed",
            prev, map_name,
        )

    def _handle_escape_tick(self) -> None:
        # Danger takes priority; abandon any target without blacklisting
        # (different map soon will reset state anyway).
        if self._engagement.state.gid is not None:
            logger.warning(
                "Danger detected, abandoning target gid=%d '%s'",
                self._engagement.state.gid, self._engagement.state.name,
            )
            self._engagement.state.clear()
        if self._idle is not None:
            self._idle.on_map_reset()

    def _resolve_engaged(
        self,
        now: float,
        died: frozenset[int],
        lost: frozenset[int],
    ) -> bool:
        """Return True if the tick should stop here (still engaged)."""
        state = self._engagement.state
        if state.gid in died:
            duration = now - state.engaged_at
            self._kills += 1
            logger.info(
                "Target killed: gid=%d name='%s' after %.2fs (kills=%d)",
                state.gid, state.name, duration, self._kills,
            )
            killed_cell = self._cells.settled_cell(state.gid, now)
            if killed_cell is not None:
                self._remember_stack_preference(
                    now,
                    preferred_cell=killed_cell,
                )
                self._reset_stack_abandon_count(killed_cell)
            state.clear()
            if self._idle is not None:
                self._idle.on_kill()
            self._stall_guard.mark_progress(now)
            return False
        if state.gid in lost:
            logger.info(
                "Target vanished (out of sight): gid=%d name='%s'",
                state.gid, state.name,
            )
            state.clear()
            self._stall_guard.mark_progress(now)
            return False
        if now - state.engaged_at > self._cfg.engagement.kill_timeout_sec:
            self._handle_kill_timeout(state, now)
            return False

        player_cell = self._read_player_cell()
        if player_cell is None:
            return True

        mob_cell = self._cells.settled_cell(state.gid, now)
        if mob_cell is None:
            ent = self._sniffer.get_entity(state.gid)
            if ent is not None and (ent.x != 0 or ent.y != 0):
                mob_cell = (ent.x, ent.y)

        abort, reason = self._player_closer.abort_engaged(
            player_cell, mob_cell,
        )
        if abort:
            logger.warning(
                "KS prio: abandoning engaged gid=%d name='%s' — %s",
                state.gid, state.name, reason,
            )
            state.clear()
            if self._cfg.engagement.player_closer_force_tp:
                self._immediate_teleport_pending = True
            self._press_abandon_target_key("ks_prio")
            if self._idle is not None:
                self._idle.on_timeout()
            return False

        if mob_cell is not None:
            for d_gid in died:
                if d_gid == state.gid:
                    continue
                dead_cell = self._cells.settled_cell(d_gid, now)
                if dead_cell != mob_cell:
                    continue
                logger.info(
                    "Stack co-kill: gid=%d died on cell %s while engaged "
                    "gid=%d name='%s'",
                    d_gid, mob_cell, state.gid, state.name,
                )
                self._remember_stack_preference(
                    now,
                    preferred_gid=state.gid,
                    preferred_cell=mob_cell,
                )
                self._stall_guard.mark_progress(now)
                state.approach_anchor_cell = player_cell
                state.approach_stationary_since = now

        if self._path_stuck.is_stuck(state, player_cell, now):
            abandon_cell = state.last_aim_cell
            self._path_stuck.abandon(state, player_cell, now)
            self._after_stack_abandon(player_cell, abandon_cell, now)
            if self._idle is not None:
                self._idle.on_timeout()
            return False

        self._approach_stall.track_player_cell(state, player_cell, now)

        settled = self._cells.settled_cell(state.gid, now)
        if settled is not None:
            ent = self._sniffer.get_entity(state.gid)
            if ent is not None and self._remote_contested.should_abandon(
                player_cell, settled, ent.hp, ent.max_hp,
            ):
                self._remote_contested.abandon(
                    state, player_cell, settled, ent.hp, ent.max_hp,
                )
                self._after_stack_abandon(player_cell, settled, now)
                if self._cfg.engagement.player_closer_force_tp:
                    self._immediate_teleport_pending = True
                self._press_abandon_target_key("ks_guard")
                if self._idle is not None:
                    self._idle.on_timeout()
                return False

            closer = self._player_closer.find_blocker(player_cell, settled)
            if closer is not None:
                self._player_closer.abandon(
                    state, player_cell, settled, closer,
                )
                self._after_stack_abandon(player_cell, settled, now)
                if self._cfg.engagement.player_closer_force_tp:
                    self._immediate_teleport_pending = True
                self._press_abandon_target_key("player_closer")
                if self._idle is not None:
                    self._idle.on_timeout()
                return False

            if self._approach_stall.is_stuck(
                state, player_cell, settled, now,
            ):
                self._approach_stall.abandon(
                    state, player_cell, settled, now,
                )
                self._after_stack_abandon(player_cell, settled, now)
                self._press_abandon_target_key("approach_stall")
                if self._idle is not None:
                    self._idle.on_timeout()
                return False

        self._engagement.continue_engagement(player_cell, now)
        return True

    def _handle_kill_timeout(self, state: TargetState, now: float) -> None:
        duration = now - state.engaged_at
        self._timeouts += 1
        assert state.gid is not None
        bl_sec = self._cfg.engagement.blacklist_sec
        logger.info(
            "Target timeout: gid=%d name='%s' after %.2fs → "
            "blacklist %.0fs (timeouts=%d)",
            state.gid, state.name, duration, bl_sec, self._timeouts,
        )
        timed_out_cell = self._cells.settled_cell(state.gid, now)
        if timed_out_cell is not None:
            self._record_stack_abandon(timed_out_cell)
            self._remember_stack_preference(
                now,
                preferred_cell=timed_out_cell,
            )
        self._blacklist.add(state.gid, bl_sec)
        state.clear()
        if self._idle is not None:
            self._idle.on_timeout()
        self._stall_guard.mark_progress(now)

    def _maybe_log_weight_snapshot(self, now: float) -> None:
        """Periodic INFO line from memory (same cadence idea as heal HP)."""
        if now - self._last_weight_log < WEIGHT_SNAPSHOT_INTERVAL_SEC:
            return
        st = self._read_player_state()
        if st is None or st.weight_max <= 0:
            return
        self._last_weight_log = now
        pct = 100.0 * st.weight / st.weight_max
        logger.info(
            "Weight snapshot: %d/%d (%.1f%%)",
            st.weight, st.weight_max, pct,
        )

    def _suppress_automation_for_death_return_survival(
        self,
        st: PlayerState | None,
    ) -> bool:
        """True while sniffer or memory HP is in the death-return band.

        :class:`~ro_bot.hunt.policies.heal.HealPolicy` uses sniffer HP; walk
        clicks use memory. Either can stay at 1 while the other glitches, so
        we suppress heal / save-teleport / idle TP if **either** source is
        critical (``0 < hp <= death_return.hp_at_most`` for sniffer — often
        **1 HP** on death; memory ``hp <= hp_at_most`` with ``hp == 0`` as
        stale / unknown).
        """
        dr = self._cfg.death_return
        if dr is None:
            return False
        hp_sn, _ = self._sniffer.get_player_hp()
        sniff_crit = 0 < hp_sn <= dr.hp_at_most
        mem_crit = (
            st is not None
            and st.hp_max > 0
            and st.hp <= dr.hp_at_most
        )
        return sniff_crit or mem_crit

    def _read_player_state(self) -> PlayerState | None:
        s = self._player_reader.read()
        if s.x == 0 and s.y == 0:
            return None
        return s

    def _read_player_cell(self) -> tuple[int, int] | None:
        s = self._read_player_state()
        if s is not None:
            return (s.x, s.y)
        sx, sy = self._sniffer.get_player_pos()
        if sx != 0 or sy != 0:
            logger.debug(
                "Using sniffer player cell (%d,%d) "
                "(memory coordinates unavailable)",
                sx, sy,
            )
            return (sx, sy)
        return None

    def _entity_hp_pair(self, gid: int) -> tuple[int, int] | None:
        ent = self._sniffer.get_entity(gid)
        if ent is None:
            return None
        return (ent.hp, ent.max_hp)

    def _sniffer_shows_trackable_mob_name(self) -> bool:
        for ent in self._sniffer.get_all_entities():
            if not ent.name:
                continue
            if (
                self._cfg.target_all_mobs
                or ent.name in self._cfg.allowed_names
            ):
                return True
        return False

    def _sniffer_shows_engageable_trackable_mob(self) -> bool:
        """Like :meth:`_sniffer_shows_trackable_mob_name` but skips
        blacklisted GIDs.

        Used by the idle-suppression branch in :meth:`_select_and_engage`
        so that we *only* defer the idle teleport while there is a
        whitelisted mob the controller can still legitimately engage —
        not when every visible whitelisted entity is in the blacklist
        (which would otherwise hold the bot AFK forever on the same
        unreachable target).
        """
        for ent in self._sniffer.get_all_entities():
            if not ent.name:
                continue
            if not (
                self._cfg.target_all_mobs
                or ent.name in self._cfg.allowed_names
            ):
                continue
            if ent.gid in self._blacklist:
                continue
            return True
        return False

    def _press_abandon_target_key(self, reason: str) -> None:
        key = self._cfg.engagement.abandon_target_key
        if not key:
            return
        try:
            self._bridge.press_key(key)
        except Exception:
            logger.exception(
                "HID press_key abandon_target_key (%s) failed (%s)",
                key, reason,
            )
            return
        logger.info(
            "Pressed abandon_target_key '%s' (%s)", key, reason,
        )

    def _select_and_engage(
        self,
        visible: list[tuple[int, str, int, int]],
        player_cell: tuple[int, int],
        now: float,
    ) -> None:
        result = collect_candidates(
            visible,
            allowed_names=self._cfg.allowed_names,
            target_all_mobs=self._cfg.target_all_mobs,
            blacklist=self._blacklist,
            cell_observer=self._cells,
            dead_zone_filter=self._dead_zone_filter,
            is_alive=self._sniffer.is_entity_alive,
            now=now,
            player_cell=player_cell,
            ks_guard_min_dist=self._cfg.engagement.ks_guard_min_dist,
            ks_guard_min_hp_deficit=(
                self._cfg.engagement.ks_guard_min_hp_deficit
            ),
            get_entity_hp=self._entity_hp_pair,
            mob_blocked_by_closer_player=(
                (lambda mob: self._player_closer.should_skip(player_cell, mob))
                if self._player_closer.enabled
                else None
            ),
        )
        if not result.candidates:
            self._log_no_candidates(now, visible, result.blocked_by_dead_zone)
            if self._idle is None:
                self._immediate_teleport_pending = False
                return
            if result.blocked_by_dead_zone != 0:
                if self._dead_zone_blocked_since is None:
                    self._dead_zone_blocked_since = now
                    self._immediate_teleport_pending = False
                    return
                blocked_for = now - self._dead_zone_blocked_since
                if blocked_for < self._cfg.engagement.dead_zone_wait_sec:
                    self._immediate_teleport_pending = False
                    return
                if self._idle.force_fire(
                    now,
                    "dead-zone blocked "
                    f"{blocked_for:.1f}s — forcing teleport",
                ):
                    self._stall_guard.mark_progress(now)
                self._dead_zone_blocked_since = now
                self._immediate_teleport_pending = False
                return
            self._dead_zone_blocked_since = None
            if self._immediate_teleport_pending:
                if self._idle.force_fire(now, "path stuck — no other candidates"):
                    self._stall_guard.mark_progress(now)
                self._immediate_teleport_pending = False
                self._all_blacklisted_since = None
            elif (
                self._cfg.idle_action is not None
                and self._cfg.idle_action.suppress_while_visible_name
                and self._sniffer_shows_engageable_trackable_mob()
            ):
                self._all_blacklisted_since = None
                self._idle.on_visible_trackable_name()
            elif (
                self._cfg.idle_action is not None
                and self._cfg.idle_action.suppress_while_visible_name
                and self._sniffer_shows_trackable_mob_name()
            ):
                # Every visible whitelisted mob is blacklisted — force TP
                # after the configured grace so we don't loop on the same
                # unreachable target. ``<= 0`` keeps the legacy behaviour.
                fire_after = self._cfg.engagement.all_blacklisted_force_tp_sec
                if fire_after <= 0:
                    self._idle.on_visible_trackable_name()
                elif self._all_blacklisted_since is None:
                    self._all_blacklisted_since = now
                    self._idle.on_visible_trackable_name()
                elif now - self._all_blacklisted_since >= fire_after:
                    stalled = now - self._all_blacklisted_since
                    if self._idle.force_fire(
                        now,
                        f"all visible candidates blacklisted for "
                        f"{stalled:.1f}s — warp out",
                    ):
                        self._stall_guard.mark_progress(now)
                    self._all_blacklisted_since = None
                else:
                    self._idle.on_visible_trackable_name()
            elif self._idle.tick(now):
                self._all_blacklisted_since = None
                self._stall_guard.mark_progress(now)
            return

        if self._should_force_stack_warp(
            player_cell, result.candidates, now,
        ):
            if self._idle is not None and self._idle.force_fire(
                now,
                "mob stack abandon ladder — warp before re-engage",
            ):
                self._stall_guard.mark_progress(now)
            self._immediate_teleport_pending = False
            return

        if self._immediate_teleport_pending:
            melee = self._cfg.engagement.stack_cell_melee_dist
            if should_defer_warp_near_stack(
                player_cell,
                result.candidates,
                preferred_cell=self._stack_preferred_cell,
                melee_dist=melee,
            ):
                self._immediate_teleport_pending = False
            elif self._idle is not None and self._idle.force_fire(
                now,
                "unreachable candidates — warp before re-engage",
            ):
                self._stall_guard.mark_progress(now)
                self._immediate_teleport_pending = False
                return
            else:
                self._immediate_teleport_pending = False

        self._dead_zone_blocked_since = None
        self._immediate_teleport_pending = False
        self._all_blacklisted_since = None
        preferred_gid, preferred_cell = self._active_stack_preference(now)
        target = pick_candidate(
            player_cell,
            result.candidates,
            preferred_gid=preferred_gid,
            preferred_cell=preferred_cell,
        )
        deferred, defer_reason = self._player_closer.hunt_deferred(player_cell)
        if deferred:
            if self._idle is not None and self._idle.force_fire(
                now, f"KS prio — {defer_reason}",
            ):
                logger.warning(
                    "KS prio: blocked engage on gid=%d — %s",
                    target.gid, defer_reason,
                )
                self._stall_guard.mark_progress(now)
            return
        if self._idle is not None:
            self._idle.on_engaged()
        self._remember_stack_preference(
            now,
            preferred_gid=target.gid,
            preferred_cell=(target.x, target.y),
        )
        self._engagement.engage(target, player_cell, now)
        self._stall_guard.mark_progress(now)

    def _clear_stack_state(self) -> None:
        self._stack_preferred_gid = None
        self._stack_preferred_cell = None
        self._stack_preferred_until = 0.0
        self._stack_cell_abandon_counts.clear()

    def _remember_stack_preference(
        self,
        now: float,
        *,
        preferred_gid: int | None = None,
        preferred_cell: tuple[int, int] | None = None,
    ) -> None:
        resume_sec = self._cfg.engagement.stack_cell_resume_sec
        if resume_sec <= 0:
            return
        if preferred_gid is not None:
            self._stack_preferred_gid = preferred_gid
        if preferred_cell is not None:
            self._stack_preferred_cell = preferred_cell
        if (
            self._stack_preferred_gid is not None
            or self._stack_preferred_cell is not None
        ):
            self._stack_preferred_until = now + resume_sec

    def _active_stack_preference(
        self,
        now: float,
    ) -> tuple[int | None, tuple[int, int] | None]:
        if now >= self._stack_preferred_until:
            return None, None
        return self._stack_preferred_gid, self._stack_preferred_cell

    def _record_stack_abandon(self, mob_cell: tuple[int, int] | None) -> None:
        if mob_cell is None:
            return
        self._stack_cell_abandon_counts[mob_cell] = (
            self._stack_cell_abandon_counts.get(mob_cell, 0) + 1
        )

    def _reset_stack_abandon_count(self, mob_cell: tuple[int, int]) -> None:
        self._stack_cell_abandon_counts.pop(mob_cell, None)

    def _after_stack_abandon(
        self,
        player_cell: tuple[int, int],
        mob_cell: tuple[int, int] | None,
        now: float,
    ) -> None:
        self._record_stack_abandon(mob_cell)
        self._remember_stack_preference(now, preferred_cell=mob_cell)
        melee = self._cfg.engagement.stack_cell_melee_dist
        if mob_cell is not None and player_near_cell(
            player_cell,
            mob_cell,
            max_dist=melee,
        ):
            return
        self._immediate_teleport_pending = True

    def _should_force_stack_warp(
        self,
        player_cell: tuple[int, int],
        candidates: list,
        now: float,
    ) -> bool:
        limit = self._cfg.engagement.stack_cell_warp_after_abandons
        if limit <= 0:
            return False
        cells: set[tuple[int, int]] = {
            (candidate.x, candidate.y) for candidate in candidates
        }
        _, preferred_cell = self._active_stack_preference(now)
        if preferred_cell is not None:
            cells.add(preferred_cell)
        melee = self._cfg.engagement.stack_cell_melee_dist
        for cell in cells:
            if self._stack_cell_abandon_counts.get(cell, 0) < limit:
                continue
            if should_defer_warp_near_stack(
                player_cell,
                candidates,
                preferred_cell=cell,
                melee_dist=melee,
            ):
                continue
            return True
        return False

    def _log_no_candidates(
        self,
        now: float,
        visible: list[tuple[int, str, int, int]],
        blocked: int,
    ) -> None:
        if now - self._last_no_candidate_log < NO_CANDIDATE_LOG_INTERVAL_SEC:
            return
        self._last_no_candidate_log = now
        parts: list[str] = []
        for gid, name, x, y in visible:
            age = self._cells.age(gid, now) or 0.0
            settled = (
                "" if age >= self._cfg.engagement.target_settle_sec
                else f" walking({age:.2f}s)"
            )
            parts.append(f"{name}@({x},{y}){settled}")
        visible_gids = {gid for gid, _, _, _ in visible}
        awaiting = [
            f"{name}@(?)"
            for gid, name in self._tracker.get_awaiting_position_entities()
            if gid not in visible_gids
        ]
        names_hint = (
            "(all mob names)"
            if self._cfg.target_all_mobs
            else sorted(self._cfg.allowed_names)
        )
        awaiting_hint = ", ".join(awaiting) if awaiting else "none"
        logger.info(
            "no candidates (allowed=%s, blacklisted=%d, "
            "dead_zone_blocked=%d, visible=%s, awaiting_pos=%s)",
            names_hint,
            len(self._blacklist),
            blocked,
            ", ".join(parts) if parts else "none",
            awaiting_hint,
        )

    # ── Sniffer-thread callbacks ────────────────────────────────────

    def _should_guard_hunt_automation(self, current_map: str) -> bool:
        route_automates = (
            self._farm_home_route is not None
            and self._farm_home_route.should_automate_on_map(current_map)
        )
        if self._is_manual_control_map(current_map) and not route_automates:
            return False
        if self._return_to_farm is not None and self._return_to_farm.is_active():
            return False
        if self._farm_home_route is not None and self._farm_home_route.is_active():
            return False
        if self._farm_arrival is not None and self._farm_arrival.is_active():
            return False
        return True

    def _maybe_recover_automation_stall(
        self,
        now: float,
        current_map: str,
    ) -> bool:
        if not self._should_guard_hunt_automation(current_map):
            self._stall_guard.mark_progress(now)
            return False
        return recover_automation_stall(
            now=now,
            guard=self._stall_guard,
            idle=self._idle,
            clear_engagement=self._engagement.state.clear,
        )

    def _on_vanish(self, gid: int, vanish_type: int) -> None:
        if vanish_type == VanishType.DIED:
            self._events.on_died(gid)
        else:
            self._events.on_lost(gid)

    def _on_map_change(self, map_name: str, _x: int, _y: int) -> None:
        old = self._map_change_listener_prev
        self._events.on_map_reset(old_map=old, new_map=map_name)
        self._map_change_listener_prev = map_name
