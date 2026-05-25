"""Engagement state machine — the tiny "fight this specific mob" FSM.

RO classic auto-attack locks onto the target after one LMB click and
keeps swinging until the mob dies or the cursor leaves the sprite.
Our job is:

  * ``engage`` — skill key (optional) + aim click on a fresh target
  * ``continue_engagement`` — re-click when the mob moves; hold fire when
    already in melee range on a stationary mob (avoids 1-cell jitter)

When ``engage_skill_key`` is set, every attack cycle is key + click —
never a bare-hand LMB.

Everything else (target selection, heal, escape, buffs, idle) is
elsewhere.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from ro_bot.core.hid.bridge import HidBridge
from ro_bot.hunt.aim_service import AimService
from ro_bot.hunt.cell_observer import CellObserver
from ro_bot.hunt.dead_zones.filter import DeadZoneFilter
from ro_bot.hunt.policies.stack_cell import manhattan_cell
from ro_bot.hunt.policies.targeting import Candidate

logger = logging.getLogger("ro_bot.hunt")


@dataclass
class TargetState:
    """Mutable state of the currently engaged mob.

    ``gid is None`` means "no target". Timestamps are monotonic. All
    timestamps are shifted on pause/resume — see
    :class:`EngagementMachine.shift`.

    ``player_cell_at_engage`` and ``engage_dist`` are snapshots taken
    when the engage click is sent, used by the path-stuck policy to
    detect "player did not move toward a distant target → click was
    rejected" (no shift needed: cell coords aren't time-based).

    ``approach_anchor_cell`` / ``approach_stationary_since`` track how
    long the player has stood still on one tile while approaching the
    mob (:class:`ApproachStallPolicy`).
    """
    gid: int | None = None
    name: str | None = None
    engaged_at: float = 0.0
    last_aim_cell: tuple[int, int] | None = None
    player_cell_at_engage: tuple[int, int] | None = None
    engage_dist: int = 0
    approach_anchor_cell: tuple[int, int] | None = None
    approach_stationary_since: float | None = None

    def clear(self) -> None:
        self.gid = None
        self.name = None
        self.engaged_at = 0.0
        self.last_aim_cell = None
        self.player_cell_at_engage = None
        self.engage_dist = 0
        self.approach_anchor_cell = None
        self.approach_stationary_since = None

    def shift(self, delta: float) -> None:
        if self.engaged_at:
            self.engaged_at += delta
        if self.approach_stationary_since is not None:
            self.approach_stationary_since += delta


class EngagementMachine:
    """Orchestrates first-engage and re-aim for a single target.

    Not responsible for target *selection* — caller picks, this class
    drives the aim/click actions.
    """

    def __init__(
        self,
        aim: AimService,
        cell_observer: CellObserver,
        dead_zone_filter: DeadZoneFilter,
        reaim_cooldown_sec: float,
        bridge: HidBridge,
        *,
        reaim_hold_dist: int = 3,
        engage_skill_key: str | None = None,
        engage_skill_delay_sec: float = 0.05,
        engage_skill_repeat_sec: float = 1.5,
    ) -> None:
        self._aim = aim
        self._cells = cell_observer
        self._dead_zones = dead_zone_filter
        self._reaim_cooldown_sec = reaim_cooldown_sec
        self._reaim_hold_dist = max(0, reaim_hold_dist)
        self._bridge = bridge
        self._engage_skill_key = (engage_skill_key or "").strip() or None
        self._engage_skill_delay_sec = max(0.0, engage_skill_delay_sec)
        self._engage_skill_repeat_sec = max(0.0, engage_skill_repeat_sec)
        self.state = TargetState()

    @property
    def _skill_only(self) -> bool:
        return self._engage_skill_key is not None

    def _press_engage_skill(self) -> bool:
        key = self._engage_skill_key
        if key is None:
            return True
        try:
            self._bridge.press_key(key)
        except Exception:
            logger.exception("Engage skill: press_key(%r) failed", key)
            return False
        if self._engage_skill_delay_sec > 0:
            time.sleep(self._engage_skill_delay_sec)
        return True

    def _aim_click_target(
        self,
        player_cell: tuple[int, int],
        target_cell: tuple[int, int],
        *,
        target_name: str | None,
    ) -> bool:
        if not self._press_engage_skill():
            return False
        return self._aim.aim_and_click(
            player_cell, target_cell, target_name=target_name,
        )

    def engage(
        self,
        candidate: Candidate,
        player_cell: tuple[int, int],
        now: float,
    ) -> None:
        """Start attacking ``candidate``: aim, settle, click."""
        cell = (candidate.x, candidate.y)
        if self._dead_zones.contains(player_cell, cell):
            logger.info(
                "Engage blocked (dead zone): gid=%d name='%s' cell=%s",
                candidate.gid,
                candidate.name,
                cell,
            )
            return
        dist = abs(cell[0] - player_cell[0]) + abs(cell[1] - player_cell[1])
        if self._skill_only:
            if not self._aim_click_target(
                player_cell, cell, target_name=candidate.name,
            ):
                return
            skill_note = f" skill='{self._engage_skill_key}'"
        else:
            if not self._aim.aim_and_click(
                player_cell, cell, target_name=candidate.name,
            ):
                return
            skill_note = ""
        self.state.gid = candidate.gid
        self.state.name = candidate.name
        self.state.engaged_at = now
        self.state.last_aim_cell = cell
        self.state.player_cell_at_engage = player_cell
        self.state.engage_dist = dist
        self.state.approach_anchor_cell = player_cell
        self.state.approach_stationary_since = now

        logger.info(
            "Engage: gid=%d name='%s' map=(%d,%d) player=(%d,%d) dist=%d%s",
            candidate.gid, candidate.name, cell[0], cell[1],
            player_cell[0], player_cell[1], dist, skill_note,
        )

    def continue_engagement(
        self,
        player_cell: tuple[int, int],
        now: float,
    ) -> None:
        """Re-click while the engaged mob is on a settled, non-HUD cell
        and the cooldown has elapsed.
        """
        if self.state.gid is None:
            return
        if not self._cells.is_visible(self.state.gid):
            return
        settled = self._cells.settled_cell(self.state.gid, now)
        if settled is None:
            return
        if now - self._aim.last_click_at < self._reaim_cooldown_sec:
            return
        if self._dead_zones.contains(player_cell, settled):
            logger.info(
                "Re-aim suppressed (dead zone): gid=%d settled=%s",
                self.state.gid, settled,
            )
            return

        dist = manhattan_cell(player_cell, settled)
        mob_stationary = settled == self.state.last_aim_cell
        in_hold = (
            self._reaim_hold_dist > 0
            and mob_stationary
            and dist <= self._reaim_hold_dist
        )
        if in_hold:
            if not self._skill_only:
                return
            repeat = max(
                self._reaim_cooldown_sec,
                self._engage_skill_repeat_sec,
            )
            if now - self._aim.last_click_at < repeat:
                return

        if mob_stationary:
            logger.debug(
                "Re-click (stationary): gid=%d at=%s",
                self.state.gid, settled,
            )
        else:
            logger.debug(
                "Re-aim: gid=%d %s→%s",
                self.state.gid, self.state.last_aim_cell, settled,
            )
        if self._skill_only:
            clicked = self._aim_click_target(
                player_cell, settled, target_name=self.state.name,
            )
        else:
            clicked = self._aim.aim_and_click(
                player_cell, settled, target_name=self.state.name,
            )
        if clicked:
            self.state.last_aim_cell = settled

    def shift(self, delta: float) -> None:
        """Pause/resume support."""
        self.state.shift(delta)
        self._aim.shift_timestamps(delta)


def sleep_aim_settle(sec: float) -> None:
    """Small re-export so callers don't depend directly on ``time``."""
    time.sleep(sec)
