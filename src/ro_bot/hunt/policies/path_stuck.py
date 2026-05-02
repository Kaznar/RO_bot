"""Path-stuck early-abandonment policy.

Why it exists: when the engage click targets a mob ``>= min_dist``
cells away, the player should immediately start running toward it.
If after ``timeout_sec`` the player's cell hasn't moved at all, the
server has clearly rejected the attack request — pathing is blocked,
the mob has already moved, or the click missed the hitbox. Waiting
the full ``kill_timeout_sec`` (typically 9–15 s) on such a target is
pure dead time.

This policy runs alongside the regular kill-timeout check in
:class:`HuntController._resolve_engaged`. It's a fast-path
abandonment: blacklist short, then let the controller pick another
candidate or trigger an immediate teleport (no idle-action grace).

Set ``min_dist <= 0`` in :class:`EngagementConfig` to disable
entirely.
"""

from __future__ import annotations

import logging

from ro_bot.hunt.blacklist import Blacklist
from ro_bot.hunt.config import EngagementConfig
from ro_bot.hunt.policies.engagement import TargetState

logger = logging.getLogger("ro_bot.hunt")


class PathStuckPolicy:
    """Detects "engaged but player isn't moving" and abandons fast."""

    def __init__(self, cfg: EngagementConfig, blacklist: Blacklist) -> None:
        self._cfg = cfg
        self._blacklist = blacklist

    def is_stuck(
        self,
        state: TargetState,
        player_cell: tuple[int, int],
        now: float,
    ) -> bool:
        """Return True iff the engage click was clearly rejected.

        Conditions:

        * policy enabled (``min_dist > 0``)
        * target was at least ``min_dist`` cells away when engaged
        * ``timeout_sec`` has elapsed since engage
        * the player is still on the exact same cell as at engage
        """
        if self._cfg.path_stuck_min_dist <= 0:
            return False
        if state.gid is None:
            return False
        if state.player_cell_at_engage is None:
            return False
        if state.engage_dist < self._cfg.path_stuck_min_dist:
            return False
        if now - state.engaged_at < self._cfg.path_stuck_timeout_sec:
            return False
        return player_cell == state.player_cell_at_engage

    def abandon(
        self,
        state: TargetState,
        player_cell: tuple[int, int],
        now: float,
    ) -> None:
        """Blacklist the target briefly and clear engagement state.

        Caller is expected to immediately retry candidate selection
        (and trigger an immediate teleport on no-candidates).
        """
        assert state.gid is not None
        gid = state.gid
        name = state.name
        bl_sec = self._cfg.path_stuck_blacklist_sec
        duration = now - state.engaged_at
        logger.warning(
            "Path stuck: gid=%d name='%s' player at %s did not move in "
            "%.2fs (engage_dist=%d) → blacklist %.0fs",
            gid, name, player_cell, duration, state.engage_dist, bl_sec,
        )
        self._blacklist.add(gid, bl_sec)
        state.clear()
