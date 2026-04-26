"""Per-GID cell-settle tracker.

Why it exists: ``tracker.get_all_positions()`` reads the destination
cell from the entity struct (memory +92/+96). RO snaps that to the
*target* of an in-progress walk immediately — but the visible sprite
slides for ~150–300 ms. Clicking on the destination before the sprite
arrives misses the hitbox and never engages auto-attack.

So: we only treat a cell as "settled" after it has been stable for
``target_settle_sec`` since the last change.
"""

from __future__ import annotations

from collections.abc import Iterable


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

        * new GID / cell changed → record ``(cell, now)``
        * cell unchanged → keep the original ``first_seen_at``
        * GIDs no longer visible → dropped (stale settled marks would
          re-engage on re-appear at a new cell)
        """
        seen: set[int] = set()
        for gid, _name, x, y in visible:
            seen.add(gid)
            cell = (x, y)
            prev = self._obs.get(gid)
            if prev is None or prev[0] != cell:
                self._obs[gid] = (cell, now)
        for gid in list(self._obs):
            if gid not in seen:
                del self._obs[gid]

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
