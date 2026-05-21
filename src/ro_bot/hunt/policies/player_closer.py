"""Skip / abandon mobs when another player is closer on the map grid.

Uses sniffer entity cache (0x0A30 name + 0x0088 stop-move position).
Other players are entities whose name is not in the hunt whitelist /
dangerous set and looks like a character name (filters garbled parses).

Set ``player_closer_margin < 0`` to disable entirely.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ro_bot.core.network.sniffer import EntityState, PacketSniffer
from ro_bot.hunt.blacklist import Blacklist
from ro_bot.hunt.config import EngagementConfig
from ro_bot.hunt.policies.engagement import TargetState
from ro_bot.hunt.policies.stack_cell import manhattan_cell

logger = logging.getLogger("ro_bot.hunt")


@dataclass(frozen=True)
class CloserPlayer:
    """Another player standing closer to the mob than we are."""
    gid: int
    name: str
    player_dist: int
    our_dist: int


def is_plausible_char_name(name: str) -> bool:
    """Reject empty, absurdly long, or garbled 0x0A30 name parses."""
    if not (2 <= len(name) <= 24):
        return False
    if not any(c.isalpha() for c in name):
        return False
    printable = sum(
        1 for c in name
        if c.isprintable() and ord(c) < 0x100
    )
    return printable >= len(name) * 0.75


def is_other_player_entity(
    ent: EntityState,
    *,
    player_gid: int,
    allowed_names: frozenset[str],
    dangerous_names: frozenset[str],
    char_name: str,
) -> bool:
    if ent.gid == player_gid:
        return False
    if not ent.name or ent.name == char_name:
        return False
    if ent.name in allowed_names or ent.name in dangerous_names:
        return False
    if ent.x == 0 and ent.y == 0:
        return False
    return is_plausible_char_name(ent.name)


def list_other_players(
    sniffer: PacketSniffer,
    *,
    allowed_names: frozenset[str],
    dangerous_names: frozenset[str],
    char_name: str,
) -> list[tuple[int, str, int, int]]:
    """Return ``(gid, name, x, y)`` for visible non-mob character entities."""
    player_gid = sniffer.get_player_gid()
    out: list[tuple[int, str, int, int]] = []
    for ent in sniffer.get_all_entities():
        if not is_other_player_entity(
            ent,
            player_gid=player_gid,
            allowed_names=allowed_names,
            dangerous_names=dangerous_names,
            char_name=char_name,
        ):
            continue
        out.append((ent.gid, ent.name, ent.x, ent.y))
    return out


def find_closer_player(
    player_cell: tuple[int, int],
    mob_cell: tuple[int, int],
    others: list[tuple[int, str, int, int]],
    *,
    margin: int,
    max_mob_dist: int,
    max_player_mob_dist: int,
) -> CloserPlayer | None:
    """Return the nearest other player who beats us to the mob by ``margin``."""
    if margin < 0:
        return None
    our_dist = manhattan_cell(player_cell, mob_cell)
    if max_mob_dist > 0 and our_dist > max_mob_dist:
        return None
    best: CloserPlayer | None = None
    for gid, name, ox, oy in others:
        their_dist = manhattan_cell((ox, oy), mob_cell)
        if max_player_mob_dist > 0 and their_dist > max_player_mob_dist:
            continue
        if their_dist + margin >= our_dist:
            continue
        if best is None or their_dist < best.player_dist:
            best = CloserPlayer(
                gid=gid,
                name=name,
                player_dist=their_dist,
                our_dist=our_dist,
            )
    return best


class PlayerCloserPolicy:
    """Filter candidates and abandon engaged targets blocked by a nearer player."""

    def __init__(
        self,
        cfg: EngagementConfig,
        blacklist: Blacklist,
        sniffer: PacketSniffer,
        *,
        allowed_names: frozenset[str],
        dangerous_names: frozenset[str],
        char_name: str,
    ) -> None:
        self._cfg = cfg
        self._blacklist = blacklist
        self._sniffer = sniffer
        self._allowed_names = allowed_names
        self._dangerous_names = dangerous_names
        self._char_name = char_name

    @property
    def enabled(self) -> bool:
        return self._cfg.player_closer_margin >= 0

    def _others(self) -> list[tuple[int, str, int, int]]:
        return list_other_players(
            self._sniffer,
            allowed_names=self._allowed_names,
            dangerous_names=self._dangerous_names,
            char_name=self._char_name,
        )

    def find_blocker(
        self,
        player_cell: tuple[int, int],
        mob_cell: tuple[int, int],
    ) -> CloserPlayer | None:
        if not self.enabled:
            return None
        return find_closer_player(
            player_cell,
            mob_cell,
            self._others(),
            margin=self._cfg.player_closer_margin,
            max_mob_dist=self._cfg.player_closer_max_mob_dist,
            max_player_mob_dist=self._cfg.player_closer_max_player_mob_dist,
        )

    def should_skip(self, player_cell: tuple[int, int], mob_cell: tuple[int, int]) -> bool:
        return self.find_blocker(player_cell, mob_cell) is not None

    def abandon(
        self,
        state: TargetState,
        player_cell: tuple[int, int],
        mob_cell: tuple[int, int],
        blocker: CloserPlayer,
    ) -> None:
        assert state.gid is not None
        gid = state.gid
        name = state.name
        bl_sec = self._cfg.player_closer_blacklist_sec
        mx, my = mob_cell
        logger.warning(
            "Player closer: gid=%d name='%s' player=%s mob=(%d,%d) "
            "our_dist=%d '%s' dist=%d → blacklist %.0fs",
            gid, name, player_cell, mx, my,
            blocker.our_dist, blocker.name, blocker.player_dist, bl_sec,
        )
        self._blacklist.add(gid, bl_sec)
        state.clear()
