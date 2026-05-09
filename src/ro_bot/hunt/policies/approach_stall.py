"""Approach-stall early abandonment (melee / uneven terrain).

If the player walks toward a mob but stops with the mob still farther
than ``approach_stall_min_dist`` cells (Manhattan), the engage click may
have brought them to a cliff edge or an unattackable tile (e.g. vertical
offset). Waiting for ``kill_timeout_sec`` wastes time.

Requires the player to stay on the same cell for
``approach_stall_timeout_sec`` while the mob's settled cell stays beyond
``approach_stall_min_dist``. Set ``approach_stall_timeout_sec <= 0`` to
disable.
"""

from __future__ import annotations

import logging

from ro_bot.hunt.blacklist import Blacklist
from ro_bot.hunt.config import EngagementConfig
from ro_bot.hunt.policies.engagement import TargetState

logger = logging.getLogger("ro_bot.hunt")


class ApproachStallPolicy:
    """Detects \"stopped walking but still not in melee range\"."""

    def __init__(self, cfg: EngagementConfig, blacklist: Blacklist) -> None:
        self._cfg = cfg
        self._blacklist = blacklist

    def track_player_cell(
        self,
        state: TargetState,
        player_cell: tuple[int, int],
        now: float,
    ) -> None:
        """Reset the stationary timer when the player enters a new cell."""
        if state.gid is None:
            return
        if state.approach_anchor_cell != player_cell:
            state.approach_anchor_cell = player_cell
            state.approach_stationary_since = now

    def is_stuck(
        self,
        state: TargetState,
        player_cell: tuple[int, int],
        mob_cell: tuple[int, int],
        now: float,
    ) -> bool:
        if self._cfg.approach_stall_timeout_sec <= 0:
            return False
        if state.gid is None:
            return False
        if state.approach_anchor_cell is None:
            return False
        if state.approach_stationary_since is None:
            return False
        px, py = player_cell
        mx, my = mob_cell
        dist = abs(mx - px) + abs(my - py)
        if dist < self._cfg.approach_stall_min_dist:
            return False
        if player_cell != state.approach_anchor_cell:
            return False
        return (
            now - state.approach_stationary_since
            >= self._cfg.approach_stall_timeout_sec
        )

    def abandon(
        self,
        state: TargetState,
        player_cell: tuple[int, int],
        mob_cell: tuple[int, int],
        now: float,
    ) -> None:
        assert state.gid is not None
        gid = state.gid
        name = state.name
        bl_sec = self._cfg.approach_stall_blacklist_sec
        px, py = player_cell
        mx, my = mob_cell
        dist = abs(mx - px) + abs(my - py)
        duration = (
            now - state.approach_stationary_since
            if state.approach_stationary_since is not None
            else 0.0
        )
        logger.warning(
            "Approach stall: gid=%d name='%s' player=%s mob=(%d,%d) dist=%d "
            "stationary %.2fs → blacklist %.0fs",
            gid, name, player_cell, mx, my, dist, duration, bl_sec,
        )
        self._blacklist.add(gid, bl_sec)
        state.clear()
