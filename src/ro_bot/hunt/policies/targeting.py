"""Candidate filtering and nearest-target picking.

Pure functions — no state, no side effects. Given a visible snapshot
and the supporting filters (whitelist, blacklist, cell observer, dead
zones, alive check), produce a clean list of clickable candidates.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ro_bot.hunt.blacklist import Blacklist
from ro_bot.hunt.cell_observer import CellObserver
from ro_bot.hunt.dead_zones.filter import DeadZoneFilter


@dataclass(frozen=True)
class Candidate:
    """A targetable mob: (gid, name, settled map cell)."""
    gid: int
    name: str
    x: int
    y: int


@dataclass(frozen=True)
class CandidateResult:
    """Output of ``collect_candidates`` — candidates plus a diagnostic
    counter for mobs that passed every filter except the dead-zone test.
    """
    candidates: list[Candidate]
    blocked_by_dead_zone: int


def collect_candidates(
    visible: list[tuple[int, str, int, int]],
    *,
    allowed_names: frozenset[str],
    target_all_mobs: bool,
    blacklist: Blacklist,
    cell_observer: CellObserver,
    dead_zone_filter: DeadZoneFilter,
    is_alive: Callable[[int], bool],
    now: float,
    player_cell: tuple[int, int],
) -> CandidateResult:
    """Filter ``visible`` into clickable candidates.

    Filters (in order, cheapest first):
      1. name in whitelist (skipped when ``target_all_mobs``)
      2. gid not in blacklist
      3. sniffer says still alive
      4. cell has been settled for ``target_settle_sec``
      5. settled cell doesn't project onto any dead zone

    The ``blocked_by_dead_zone`` counter tells the caller whether "no
    candidates" means *nothing visible* (fire idle action) vs. *mob
    behind HUD* (wait — it'll walk out).
    """
    candidates: list[Candidate] = []
    blocked = 0
    for gid, name, _x, _y in visible:
        if not target_all_mobs and name not in allowed_names:
            continue
        if gid in blacklist:
            continue
        if not is_alive(gid):
            continue
        settled = cell_observer.settled_cell(gid, now)
        if settled is None:
            continue
        if dead_zone_filter.contains(player_cell, settled):
            blocked += 1
            continue
        candidates.append(Candidate(gid=gid, name=name, x=settled[0], y=settled[1]))
    return CandidateResult(
        candidates=candidates, blocked_by_dead_zone=blocked,
    )


def pick_nearest(
    player_cell: tuple[int, int],
    candidates: list[Candidate],
) -> Candidate:
    """Nearest by Manhattan distance. Ties broken by GID for stability."""
    px, py = player_cell
    return min(
        candidates,
        key=lambda c: (abs(c.x - px) + abs(c.y - py), c.gid),
    )
