"""Helpers for multiple mobs sharing one map cell.

RO clients often stack sprites on one tile; the engaged GID may differ
from the mob the client is actually hitting. These helpers pick a
preferred target after stack kills and decide when a nearby pile should
defer warp recovery.
"""

from __future__ import annotations

from ro_bot.hunt.policies.targeting import Candidate, pick_nearest


def manhattan_cell(
    a: tuple[int, int],
    b: tuple[int, int],
) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def player_near_cell(
    player_cell: tuple[int, int],
    mob_cell: tuple[int, int],
    *,
    max_dist: int,
) -> bool:
    if max_dist <= 0:
        return False
    return manhattan_cell(player_cell, mob_cell) <= max_dist


def pick_candidate(
    player_cell: tuple[int, int],
    candidates: list[Candidate],
    *,
    preferred_gid: int | None = None,
    preferred_cell: tuple[int, int] | None = None,
) -> Candidate:
    """Prefer a remembered GID, then any mob on a remembered cell."""
    if preferred_gid is not None:
        for candidate in candidates:
            if candidate.gid == preferred_gid:
                return candidate
    if preferred_cell is not None:
        at_stack = [
            candidate
            for candidate in candidates
            if (candidate.x, candidate.y) == preferred_cell
        ]
        if at_stack:
            return min(
                at_stack,
                key=lambda c: (
                    manhattan_cell(player_cell, (c.x, c.y)),
                    c.gid,
                ),
            )
    return pick_nearest(player_cell, candidates)


def should_defer_warp_near_stack(
    player_cell: tuple[int, int],
    candidates: list[Candidate],
    *,
    preferred_cell: tuple[int, int] | None,
    melee_dist: int,
) -> bool:
    """True when the player is already in melee range of a candidate pile."""
    for candidate in candidates:
        if player_near_cell(
            player_cell,
            (candidate.x, candidate.y),
            max_dist=melee_dist,
        ):
            return True
    if preferred_cell is None:
        return False
    if not player_near_cell(player_cell, preferred_cell, max_dist=melee_dist):
        return False
    return any(
        (candidate.x, candidate.y) == preferred_cell
        for candidate in candidates
    )
