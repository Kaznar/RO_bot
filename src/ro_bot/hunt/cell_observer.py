"""Per-GID cell-settle tracker.

Why it exists: ``tracker.get_all_positions()`` reads the destination
cell from the entity struct (memory +92/+96). RO snaps that to the
*target* of an in-progress walk immediately — but the visible sprite
slides for ~150–300 ms. Clicking on the destination before the sprite
arrives misses the hitbox and never engages auto-attack.

So: we only treat a cell as "settled" after it has been stable for
``target_settle_sec`` since the last change.

Burst merging: RO mobs walk in short bursts of 3–4 cells in <1 s,
then idle for several seconds. Each cell hop in such a burst would
naively reset the settle timer and starve engagement. If a new cell
change arrives within ``BURST_MERGE_SEC`` of the previous one we
treat it as part of the same move — keep the original
``first_seen_at`` and only update the cell. The settle timer thus
counts from the *start* of the burst, which is what a human player
would intuit as "the move".

Emits DEBUG-level transition logs (new / cell-change / burst-merge /
dropped) so cell stability can be measured and the threshold tuned
empirically.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

logger = logging.getLogger("ro_bot.hunt")

# Cell changes arriving within this window are folded into the previous
# observation (same "move") instead of resetting settle. Tuned from
# real-world data: bursts are typically <0.3 s/hop, single legitimate
# walks rarely re-trigger inside 0.5 s.
BURST_MERGE_SEC: float = 0.5


class CellObserver:
    """Tracks ``gid → (cell, first_seen_at)`` and answers settled queries."""

    def __init__(self, settle_sec: float) -> None:
        self._settle_sec = settle_sec
        self._obs: dict[int, tuple[tuple[int, int], float]] = {}

    def update(
        self,
        visible: Iterable[tuple[int, str, int, int]],
        now: float,
    ) -> None:
        """Refresh state from the current visible snapshot.

        * new GID → record ``(cell, now)``
        * cell changed within ``BURST_MERGE_SEC`` → keep the original
          ``first_seen_at`` (burst merge), update the cell
        * cell changed after a real pause → reset ``first_seen_at``
        * cell unchanged → keep the original ``first_seen_at``
        * GIDs no longer visible → dropped (stale settled marks would
          re-engage on re-appear at a new cell)
        """
        seen: set[int] = set()
        for gid, name, x, y in visible:
            seen.add(gid)
            cell = (x, y)
            prev = self._obs.get(gid)
            if prev is None:
                self._obs[gid] = (cell, now)
                logger.debug(
                    "cell-observer: gid=%d name=%r new at %s",
                    gid, name, cell,
                )
                continue
            prev_cell, prev_since = prev
            if prev_cell == cell:
                continue
            prev_age = now - prev_since
            if prev_age < BURST_MERGE_SEC:
                self._obs[gid] = (cell, prev_since)
                logger.debug(
                    "cell-observer: gid=%d name=%r %s→%s "
                    "burst-merge (prev_age=%.2fs)",
                    gid, name, prev_cell, cell, prev_age,
                )
            else:
                self._obs[gid] = (cell, now)
                logger.debug(
                    "cell-observer: gid=%d name=%r %s→%s "
                    "(prev_age=%.2fs)",
                    gid, name, prev_cell, cell, prev_age,
                )
        for gid in list(self._obs):
            if gid not in seen:
                prev_cell, prev_since = self._obs[gid]
                del self._obs[gid]
                logger.debug(
                    "cell-observer: gid=%d dropped "
                    "(last_cell=%s, last_age=%.2fs)",
                    gid, prev_cell, now - prev_since,
                )

    def settled_cell(
        self, gid: int, now: float,
    ) -> tuple[int, int] | None:
        """Return the settled cell of ``gid`` or None if still mid-walk."""
        obs = self._obs.get(gid)
        if obs is None:
            return None
        cell, since = obs
        if now - since < self._settle_sec:
            return None
        return cell

    def is_visible(self, gid: int) -> bool:
        return gid in self._obs

    def age(self, gid: int, now: float) -> float | None:
        obs = self._obs.get(gid)
        return None if obs is None else now - obs[1]

    def clear(self) -> None:
        self._obs.clear()

    def shift(self, delta: float) -> None:
        """Shift all timestamps by ``delta`` (pause/resume)."""
        if not self._obs:
            return
        self._obs = {
            gid: (cell, since + delta)
            for gid, (cell, since) in self._obs.items()
        }
