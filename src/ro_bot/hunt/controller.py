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

Everything heavy lives in submodules (policies / state containers).
This file is the glue.
"""

from __future__ import annotations

import logging
import time

from ro_bot.core.hid.bridge import HidBridge
from ro_bot.core.memory.player_state import PlayerReader
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
    NO_CANDIDATE_LOG_INTERVAL_SEC,
)
from ro_bot.hunt.dead_zones.filter import DeadZoneFilter
from ro_bot.hunt.event_bus import EventBus
from ro_bot.hunt.pause import PauseToken
from ro_bot.hunt.policies.buffs import BuffPolicy
from ro_bot.hunt.policies.engagement import EngagementMachine, TargetState
from ro_bot.hunt.policies.escape import EscapePolicy
from ro_bot.hunt.policies.heal import HealPolicy
from ro_bot.hunt.policies.idle_action import IdleActionPolicy
from ro_bot.hunt.policies.path_stuck import PathStuckPolicy
from ro_bot.hunt.policies.return_to_farm import ReturnToFarmPolicy
from ro_bot.hunt.policies.targeting import collect_candidates, pick_nearest

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
    ) -> None:
        self._cfg = cfg
        self._bridge = bridge
        self._sniffer = sniffer
        self._tracker = tracker
        self._player_reader = player_reader

        self._events = EventBus()
        self._cells = CellObserver(cfg.engagement.target_settle_sec)
        self._blacklist = Blacklist()
        self._pause = PauseToken()

        self._engagement = EngagementMachine(
            aim=aim,
            cell_observer=self._cells,
            dead_zone_filter=dead_zone_filter,
            reaim_cooldown_sec=cfg.engagement.reaim_click_cooldown_sec,
        )
        self._path_stuck = PathStuckPolicy(cfg.engagement, self._blacklist)

        self._heal = (
            HealPolicy(cfg.heal, bridge, sniffer, cfg.allowed_maps)
            if cfg.heal is not None else None
        )
        self._buffs = BuffPolicy(cfg.buffs, bridge, sniffer, cfg.allowed_maps)
        self._idle = (
            IdleActionPolicy(cfg.idle_action, bridge)
            if cfg.idle_action is not None else None
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

        self._dead_zone_filter = dead_zone_filter

        self._installed = False
        self._kills = 0
        self._timeouts = 0
        self._last_no_candidate_log: float = 0.0
        # Set by path-stuck abandonment; consumed once by the next
        # candidate-selection pass to bypass idle grace when nothing
        # else is reachable.
        self._immediate_teleport_pending: bool = False

    # ── Lifecycle ───────────────────────────────────────────────────

    def install(self) -> None:
        """Subscribe to sniffer events. Call once before ticking."""
        if self._installed:
            return
        self._sniffer.add_entity_vanish_listener(self._on_vanish)
        self._sniffer.add_map_change_listener(self._on_map_change)
        self._buffs.install()
        self._installed = True
        logger.info(
            "HuntController installed: char='%s' allowed=%s maps=%s "
            "timeout=%.1fs blacklist=%.0fs dead_zones=%d",
            self._cfg.char_name,
            sorted(self._cfg.allowed_names),
            sorted(self._cfg.allowed_maps),
            self._cfg.engagement.kill_timeout_sec,
            self._cfg.engagement.blacklist_sec,
            len(self._cfg.dead_zones),
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
        if self._last_no_candidate_log:
            self._last_no_candidate_log += delta
        logger.info("Resumed after %.1fs paused", delta)

    # ── Tick interval ───────────────────────────────────────────────

    def tick_interval_sec(self) -> float:
        if self._pause.is_paused:
            return IDLE_POLL_SEC
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

        if self._heal is not None:
            self._heal.tick(now)
        self._buffs.tick(now)

        events = self._events.drain()
        if events.map_reset:
            self._handle_map_reset()
            return

        self._blacklist.expire(now)

        visible = self._tracker.get_all_positions()
        self._cells.update(visible, now)

        if self._escape is not None and self._escape.press_if_ready(now):
            self._handle_escape_tick()
            return

        if self._return_to_farm is not None and self._return_to_farm.is_active():
            if self._engagement.state.gid is not None:
                # We may have engaged something on the farm map just
                # before walking through the warp. Drop it — that GID
                # isn't on this map anyway.
                self._engagement.state.clear()
            self._return_to_farm.tick(now)
            return

        if self._engagement.state.gid is not None:
            if self._resolve_engaged(now, events.died_gids, events.lost_gids):
                return
            # Fell through: target was killed/lost/timed-out. Continue
            # into candidate selection with a fresh slate.

        player_cell = self._read_player_cell()
        if player_cell is None:
            return

        self._select_and_engage(visible, player_cell, now)

    # ── Helpers ─────────────────────────────────────────────────────

    def _handle_map_reset(self) -> None:
        map_name = self._sniffer.get_map_name() or "?"
        allowed = (
            "allowed" if map_name in self._cfg.allowed_maps
            else "skip-consumables"
        )
        logger.info("Map change → %s (%s) → reset hunt state", map_name, allowed)
        self._engagement.state.clear()
        self._blacklist.clear()
        self._cells.clear()
        self._immediate_teleport_pending = False
        if self._idle is not None:
            self._idle.on_map_reset()
        if self._return_to_farm is not None:
            self._return_to_farm.on_map_change(map_name, time.monotonic())

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
            state.clear()
            if self._idle is not None:
                self._idle.on_kill()
            return False
        if state.gid in lost:
            logger.info(
                "Target vanished (out of sight): gid=%d name='%s'",
                state.gid, state.name,
            )
            state.clear()
            return False
        if now - state.engaged_at > self._cfg.engagement.kill_timeout_sec:
            self._handle_kill_timeout(state, now)
            return False

        player_cell = self._read_player_cell()
        if player_cell is None:
            return True

        if self._path_stuck.is_stuck(state, player_cell, now):
            self._path_stuck.abandon(state, player_cell, now)
            self._immediate_teleport_pending = True
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
        self._blacklist.add(state.gid, bl_sec)
        state.clear()
        if self._idle is not None:
            self._idle.on_timeout()

    def _read_player_cell(self) -> tuple[int, int] | None:
        state = self._player_reader.read()
        if state.x == 0 and state.y == 0:
            return None
        return (state.x, state.y)

    def _select_and_engage(
        self,
        visible: list[tuple[int, str, int, int]],
        player_cell: tuple[int, int],
        now: float,
    ) -> None:
        result = collect_candidates(
            visible,
            allowed_names=self._cfg.allowed_names,
            blacklist=self._blacklist,
            cell_observer=self._cells,
            dead_zone_filter=self._dead_zone_filter,
            is_alive=self._sniffer.is_entity_alive,
            now=now,
            player_cell=player_cell,
        )
        if not result.candidates:
            self._log_no_candidates(now, visible, result.blocked_by_dead_zone)
            # Mobs hidden behind the HUD: don't teleport — they'll walk out.
            if self._idle is None or result.blocked_by_dead_zone != 0:
                self._immediate_teleport_pending = False
                return
            if self._immediate_teleport_pending:
                self._idle.force_fire(now, "path stuck — no other candidates")
                self._immediate_teleport_pending = False
            else:
                self._idle.tick(now)
            return

        self._immediate_teleport_pending = False
        target = pick_nearest(player_cell, result.candidates)
        if self._idle is not None:
            self._idle.on_engaged()
        self._engagement.engage(target, player_cell, now)

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
        logger.info(
            "no candidates (allowed=%s, blacklisted=%d, "
            "dead_zone_blocked=%d, visible=%s)",
            sorted(self._cfg.allowed_names),
            len(self._blacklist),
            blocked,
            ", ".join(parts) if parts else "none",
        )

    # ── Sniffer-thread callbacks ────────────────────────────────────

    def _on_vanish(self, gid: int, vanish_type: int) -> None:
        if vanish_type == VanishType.DIED:
            self._events.on_died(gid)
        else:
            self._events.on_lost(gid)

    def _on_map_change(self, _map: str, _x: int, _y: int) -> None:
        self._events.on_map_reset()
