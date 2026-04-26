"""Engagement state machine — the tiny "fight this specific mob" FSM.

RO classic auto-attack locks onto the target after one LMB click and
keeps swinging until the mob dies or the cursor leaves the sprite.
Our job is:

  * ``engage`` — aim at the first click (fresh target)
  * ``continue_engagement`` — re-aim only when the mob walks to a new,
    settled cell and cooldown has elapsed

Everything else (target selection, heal, escape, buffs, idle) is
elsewhere.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from ro_bot.hunt.aim_service import AimService
from ro_bot.hunt.cell_observer import CellObserver
from ro_bot.hunt.dead_zones.filter import DeadZoneFilter
from ro_bot.hunt.policies.targeting import Candidate

logger = logging.getLogger("ro_bot.hunt")


@dataclass
class TargetState:
    """Mutable state of the currently engaged mob.

    ``gid is None`` means "no target". Timestamps are monotonic. All
    timestamps are shifted on pause/resume — see
    :class:`EngagementMachine.shift`.
    """
    gid: int | None = None
    name: str | None = None
    engaged_at: float = 0.0
    last_aim_cell: tuple[int, int] | None = None

    def clear(self) -> None:
        self.gid = None
        self.name = None
        self.engaged_at = 0.0
        self.last_aim_cell = None

    def shift(self, delta: float) -> None:
        if self.engaged_at:
            self.engaged_at += delta


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
    ) -> None:
        self._aim = aim
        self._cells = cell_observer
        self._dead_zones = dead_zone_filter
        self._reaim_cooldown_sec = reaim_cooldown_sec
        self.state = TargetState()

    def engage(
        self,
        candidate: Candidate,
        player_cell: tuple[int, int],
        now: float,
    ) -> None:
        """Start attacking ``candidate``: aim, settle, click."""
        cell = (candidate.x, candidate.y)
        self.state.gid = candidate.gid
        self.state.name = candidate.name
        self.state.engaged_at = now
        self.state.last_aim_cell = cell

        self._aim.aim_and_click(player_cell, cell)

        dist = abs(cell[0] - player_cell[0]) + abs(cell[1] - player_cell[1])
        logger.info(
            "Engage: gid=%d name='%s' map=(%d,%d) player=(%d,%d) dist=%d",
            candidate.gid, candidate.name, cell[0], cell[1],
            player_cell[0], player_cell[1], dist,
        )

    def continue_engagement(
        self,
        player_cell: tuple[int, int],
        now: float,
    ) -> None:
        """Re-aim and re-click only when the engaged mob has walked to
        a new, settled, non-HUD cell and the cooldown has elapsed.
        """
        if self.state.gid is None:
            return
        if not self._cells.is_visible(self.state.gid):
            return
        settled = self._cells.settled_cell(self.state.gid, now)
        if settled is None:
            return
        if settled == self.state.last_aim_cell:
            return
        if now - self._aim.last_click_at < self._reaim_cooldown_sec:
            return
        if self._dead_zones.contains(player_cell, settled):
            logger.debug(
                "Re-aim suppressed (dead zone): gid=%d settled=%s",
                self.state.gid, settled,
            )
            return

        logger.debug(
            "Re-aim: gid=%d %s→%s",
            self.state.gid, self.state.last_aim_cell, settled,
        )
        self._aim.aim_and_click(player_cell, settled)
        self.state.last_aim_cell = settled

    def shift(self, delta: float) -> None:
        """Pause/resume support."""
        self.state.shift(delta)
        self._aim.shift_timestamps(delta)


def sleep_aim_settle(sec: float) -> None:
    """Small re-export so callers don't depend directly on ``time``."""
    time.sleep(sec)
