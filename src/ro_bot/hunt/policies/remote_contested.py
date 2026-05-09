"""Kill-steal guard: skip distant mobs that are already losing HP.

When another player is attacking a mob, packets usually show ``hp <
max_hp`` while the mob is still several cells away. Targeting such mobs
looks like KS. Filter them during candidate collection and abandon if we
already engaged one.

Set ``ks_guard_min_dist <= 0`` to disable entirely.
"""

from __future__ import annotations

import logging

from ro_bot.hunt.blacklist import Blacklist
from ro_bot.hunt.config import EngagementConfig
from ro_bot.hunt.policies.engagement import TargetState
from ro_bot.hunt.policies.targeting import is_remote_contested_mob

logger = logging.getLogger("ro_bot.hunt")


class RemoteContestedPolicy:
    """Abandon current target when it matches the remote-contested rule."""

    def __init__(self, cfg: EngagementConfig, blacklist: Blacklist) -> None:
        self._cfg = cfg
        self._blacklist = blacklist

    def should_abandon(
        self,
        player_cell: tuple[int, int],
        mob_cell: tuple[int, int],
        hp: int,
        max_hp: int,
    ) -> bool:
        return is_remote_contested_mob(
            player_cell,
            mob_cell,
            hp,
            max_hp,
            min_dist=self._cfg.ks_guard_min_dist,
            min_hp_deficit=self._cfg.ks_guard_min_hp_deficit,
        )

    def abandon(
        self,
        state: TargetState,
        player_cell: tuple[int, int],
        mob_cell: tuple[int, int],
        hp: int,
        max_hp: int,
    ) -> None:
        assert state.gid is not None
        gid = state.gid
        name = state.name
        bl_sec = self._cfg.ks_guard_blacklist_sec
        mx, my = mob_cell
        logger.warning(
            "KS guard: gid=%d name='%s' player=%s mob=(%d,%d) HP=%d/%d "
            "→ blacklist %.0fs",
            gid, name, player_cell, mx, my, hp, max_hp, bl_sec,
        )
        self._blacklist.add(gid, bl_sec)
        state.clear()
