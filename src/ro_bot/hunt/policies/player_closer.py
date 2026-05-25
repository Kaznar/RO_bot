"""Skip / abandon mobs when another player is closer on the map grid.

Uses sniffer entity cache (0x0A30 name + 0x0088 stop-move position).

Mob-vs-player discrimination is GID-range first (on this server player
account IDs sit in ``[player_gid_min, player_gid_max)``, commonly
3 000 000–4 000 000, while mob unique IDs are 100 000 000+). An entity
in that range with a known map cell counts as another player even when
the 0x0A30 name packet has not arrived yet (stop-move only). When the
GID range is disabled (``player_gid_max <= 0``), fall back to the
name-only heuristic (``is_plausible_char_name``).

``player_near_mob_radius`` (e.g. 10) skips any mob when another player
is within that many cells — even when we are closer after a teleport.

Set ``player_closer_margin < 0`` and ``player_near_mob_radius <= 0`` to
disable the policy entirely.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from ro_bot.core.network.sniffer import EntityState, PacketSniffer
from ro_bot.hunt.blacklist import Blacklist
from ro_bot.hunt.config import EngagementConfig
from ro_bot.hunt.policies.engagement import TargetState
from ro_bot.hunt.policies.stack_cell import manhattan_cell

logger = logging.getLogger("ro_bot.hunt")


@dataclass(frozen=True)
class CloserPlayer:
    """Another player blocking a mob (closer or within ``near_mob_radius``)."""
    gid: int
    name: str
    player_dist: int
    our_dist: int
    reason: str = "closer"


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


def player_display_name(ent: EntityState) -> str:
    """Label for logs when 0x0A30 name is missing or garbled."""
    if ent.name and is_plausible_char_name(ent.name):
        return ent.name
    return f"player#{ent.gid}"


def is_in_player_gid_range(
    gid: int,
    *,
    player_gid: int,
    player_gid_min: int,
    player_gid_max: int,
) -> bool:
    if gid == player_gid:
        return False
    if player_gid_max <= 0:
        return False
    if gid >= player_gid_max:
        return False
    if player_gid_min > 0 and gid < player_gid_min:
        return False
    return True


def _name_conflicts_with_player_filters(
    name: str,
    *,
    char_name: str,
    allowed_names: frozenset[str],
    dangerous_names: frozenset[str],
) -> bool:
    if not name or name == char_name:
        return True
    return name in allowed_names or name in dangerous_names


def is_other_player_entity(
    ent: EntityState,
    *,
    player_gid: int,
    allowed_names: frozenset[str],
    dangerous_names: frozenset[str],
    char_name: str,
    player_gid_min: int,
    player_gid_max: int,
    require_position: bool = True,
) -> bool:
    if require_position and ent.x == 0 and ent.y == 0:
        return False
    if is_in_player_gid_range(
        ent.gid,
        player_gid=player_gid,
        player_gid_min=player_gid_min,
        player_gid_max=player_gid_max,
    ):
        # GID range is authoritative — empty name is normal for stop-move-only.
        if ent.name == char_name:
            return False
        if ent.name and (
            ent.name in allowed_names or ent.name in dangerous_names
        ):
            return False
        return True
    if player_gid_max > 0:
        return False
    if _name_conflicts_with_player_filters(
        ent.name,
        char_name=char_name,
        allowed_names=allowed_names,
        dangerous_names=dangerous_names,
    ):
        return False
    return is_plausible_char_name(ent.name)


def list_other_players(
    sniffer: PacketSniffer,
    *,
    allowed_names: frozenset[str],
    dangerous_names: frozenset[str],
    char_name: str,
    player_gid_min: int,
    player_gid_max: int,
    require_position: bool = True,
) -> list[tuple[int, str, int, int]]:
    """Return ``(gid, name, x, y)`` for visible non-mob character entities."""
    player_gid = sniffer.get_player_gid()
    out: list[tuple[int, str, int, int]] = []
    for ent in sniffer.snapshot_entities(require_name=False):
        if not is_other_player_entity(
            ent,
            player_gid=player_gid,
            allowed_names=allowed_names,
            dangerous_names=dangerous_names,
            char_name=char_name,
            player_gid_min=player_gid_min,
            player_gid_max=player_gid_max,
            require_position=require_position,
        ):
            continue
        out.append((ent.gid, player_display_name(ent), ent.x, ent.y))
    return out


def _positioned_players(
    others: list[tuple[int, str, int, int]],
) -> list[tuple[int, str, int, int]]:
    return [(g, n, x, y) for g, n, x, y in others if x != 0 or y != 0]


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
        if ox == 0 and oy == 0:
            continue
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


def find_player_near_mob(
    player_cell: tuple[int, int],
    mob_cell: tuple[int, int],
    others: list[tuple[int, str, int, int]],
    *,
    near_mob_radius: int,
    max_mob_dist: int,
) -> CloserPlayer | None:
    """Return a player within ``near_mob_radius`` cells of the mob (any direction)."""
    if near_mob_radius <= 0:
        return None
    our_dist = manhattan_cell(player_cell, mob_cell)
    if max_mob_dist > 0 and our_dist > max_mob_dist:
        return None
    best: CloserPlayer | None = None
    for gid, name, ox, oy in others:
        if ox == 0 and oy == 0:
            continue
        their_dist = manhattan_cell((ox, oy), mob_cell)
        if their_dist > near_mob_radius:
            continue
        if best is None or their_dist < best.player_dist:
            best = CloserPlayer(
                gid=gid,
                name=name,
                player_dist=their_dist,
                our_dist=our_dist,
                reason="near_mob",
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
        self._last_other_player_at: float | None = None

    def on_map_reset(self) -> None:
        self._last_other_player_at = None

    @property
    def enabled(self) -> bool:
        return (
            self._cfg.player_closer_margin >= 0
            or self._cfg.player_near_mob_radius > 0
            or self._cfg.player_near_bot_radius > 0
            or self._cfg.player_defer_hunt_if_visible
            or self._cfg.player_visible_grace_sec > 0
        )

    def _others(self, *, require_position: bool = False) -> list[tuple[int, str, int, int]]:
        return list_other_players(
            self._sniffer,
            allowed_names=self._allowed_names,
            dangerous_names=self._dangerous_names,
            char_name=self._char_name,
            player_gid_min=self._cfg.player_gid_min,
            player_gid_max=self._cfg.player_gid_max,
            require_position=require_position,
        )

    def visible_other_players(self) -> list[tuple[int, str, int, int]]:
        """Other players currently in the sniffer cache (GID range + cell)."""
        if not self.enabled:
            return []
        return self._others(require_position=False)

    def _format_player_labels(
        self,
        others: list[tuple[int, str, int, int]],
        *,
        limit: int = 2,
    ) -> str:
        labels = ", ".join(
            f"{name}@({x},{y})" if x or y else f"{name}@(?)"
            for _, name, x, y in others[:limit]
        )
        if len(others) > limit:
            labels += f", +{len(others) - limit} more"
        return labels

    def hunt_deferred(self, player_cell: tuple[int, int]) -> tuple[bool, str]:
        """True when KS priority forbids starting new engagements."""
        if not self.enabled:
            return False, ""
        now = time.monotonic()
        others = self._others(require_position=False)
        grace = self._cfg.player_visible_grace_sec
        if others:
            self._last_other_player_at = now
        elif (
            grace > 0
            and self._last_other_player_at is not None
            and now - self._last_other_player_at < grace
        ):
            elapsed = now - self._last_other_player_at
            return True, (
                f"player grace {elapsed:.0f}s / {grace:.0f}s since last sighting"
            )
        if not others:
            return False, ""
        if self._cfg.player_defer_hunt_if_visible:
            return True, (
                f"other player(s) visible ({self._format_player_labels(others)})"
            )
        near_bot = self._cfg.player_near_bot_radius
        if near_bot > 0:
            for _, name, ox, oy in _positioned_players(others):
                d = manhattan_cell(player_cell, (ox, oy))
                if d <= near_bot:
                    return True, f"'{name}' within {near_bot} cells of bot"
        return False, ""

    def abort_engaged(
        self,
        player_cell: tuple[int, int],
        mob_cell: tuple[int, int] | None = None,
    ) -> tuple[bool, str]:
        """True when an in-flight target must be dropped (KS mid-fight)."""
        deferred, reason = self.hunt_deferred(player_cell)
        if deferred:
            return True, reason
        if mob_cell is None:
            return False, ""
        blocker = self.find_blocker(player_cell, mob_cell)
        if blocker is None:
            return False, ""
        return True, (
            f"player '{blocker.name}' {blocker.reason} "
            f"(player_dist={blocker.player_dist}, our_dist={blocker.our_dist})"
        )

    def find_blocker(
        self,
        player_cell: tuple[int, int],
        mob_cell: tuple[int, int],
    ) -> CloserPlayer | None:
        if not self.enabled:
            return None
        others = _positioned_players(self._others(require_position=True))
        near = find_player_near_mob(
            player_cell,
            mob_cell,
            others,
            near_mob_radius=self._cfg.player_near_mob_radius,
            max_mob_dist=0,
        )
        if near is not None:
            return near
        if self._cfg.player_closer_margin < 0:
            return None
        return find_closer_player(
            player_cell,
            mob_cell,
            others,
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
            "Player closer (%s): gid=%d name='%s' player=%s mob=(%d,%d) "
            "our_dist=%d '%s' dist=%d → blacklist %.0fs",
            blocker.reason,
            gid, name, player_cell, mx, my,
            blocker.our_dist, blocker.name, blocker.player_dist, bl_sec,
        )
        self._blacklist.add(gid, bl_sec)
        state.clear()
