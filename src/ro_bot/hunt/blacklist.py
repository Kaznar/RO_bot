"""Time-based GID blacklist.

When the controller gives up on a target (``kill_timeout_sec`` elapsed
without a death), we push its GID in here for ``blacklist_sec`` so
targeting skips it until a configurable cooldown elapses. Long enough
that the mob has time to wander to a reachable cell.
"""

from __future__ import annotations

import time


class Blacklist:
    """GID → expiry (monotonic time) map with ``expire``/``contains`` API."""

    def __init__(self) -> None:
        self._entries: dict[int, float] = {}

    def add(self, gid: int, duration_sec: float) -> None:
        self._entries[gid] = time.monotonic() + duration_sec

    def __contains__(self, gid: object) -> bool:
        return isinstance(gid, int) and gid in self._entries

    def expire(self, now: float | None = None) -> list[int]:
        """Remove and return all GIDs whose expiry is ≤ ``now``."""
        if now is None:
            now = time.monotonic()
        expired = [g for g, exp in self._entries.items() if exp <= now]
        for gid in expired:
            del self._entries[gid]
        return expired

    def clear(self) -> None:
        self._entries.clear()

    def shift(self, delta: float) -> None:
        """Add ``delta`` seconds to every entry's expiry (pause/resume)."""
        if not self._entries:
            return
        self._entries = {gid: exp + delta for gid, exp in self._entries.items()}

    def __len__(self) -> int:
        return len(self._entries)
