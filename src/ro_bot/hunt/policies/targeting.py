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


def is_remote_contested_mob(
    player_cell: tuple[int, int],
    mob_cell: tuple[int, int],
    hp: int,
    max_hp: int,
    *,
    min_dist: int,
    min_hp_deficit: int,
) -> bool:
    """True if the mob is far enough and already damaged (someone else hit it)."""
    if min_dist <= 0:
        return False
    if min_hp_deficit <= 0:
        return False
    if max_hp <= 0:
        return False
    if max_hp - hp < min_hp_deficit:
        return False
    px, py = player_cell
    mx, my = mob_cell
    dist = abs(mx - px) + abs(my - py)
    return dist >= min_dist


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
    ks_guard_min_dist: int = 0,
    ks_guard_min_hp_deficit: int = 1,
    get_entity_hp: Callable[[int], tuple[int, int] | None] | None = None,
) -> CandidateResult:
    """Filter ``visible`` into clickable candidates.

    Filters (in order, cheapest first):
      1. name in whitelist (skipped when ``target_all_mobs``)
      2. gid not in blacklist
      3. sniffer says still alive
      4. cell has been settled for ``target_settle_sec``
      5. settled cell doesn't project onto any dead zone
      6. optional KS guard — distant mobs that already lost HP

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
        if ks_guard_min_dist > 0 and get_entity_hp is not None:
            hp_pair = get_entity_hp(gid)
            if hp_pair is not None:
                hp_e, max_hp_e = hp_pair
                if is_remote_contested_mob(
                    player_cell,
                    settled,
                    hp_e,
                    max_hp_e,
                    min_dist=ks_guard_min_dist,
                    min_hp_deficit=ks_guard_min_hp_deficit,
                ):
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
