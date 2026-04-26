"""Thread-safe handoff for sniffer events to the tick thread.

Sniffer callbacks fire on the scapy thread; the controller tick runs
on the main thread. We can't take actions on the sniffer thread
(Arduino calls block; state updates want serial ordering), so we
accumulate event IDs in sets and drain them on the next tick.

Events tracked:
  * died GIDs      — confirmed kills (vanish type=DIED)
  * lost GIDs      — non-death vanishes (out of sight / teleport / logout)
  * map_reset flag — map change observed

Not a general pub-sub bus; just what the hunt controller needs.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class TickEvents:
    """Snapshot of events that fired since the previous drain."""
    died_gids: frozenset[int]
    lost_gids: frozenset[int]
    map_reset: bool


class EventBus:
    """Thread-safe accumulator for sniffer events.

    Writers (sniffer thread) call ``on_*``; reader (tick thread) calls
    :meth:`drain` once per tick.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._died: set[int] = set()
        self._lost: set[int] = set()
        self._map_reset: bool = False

    def on_died(self, gid: int) -> None:
        with self._lock:
            self._died.add(gid)

    def on_lost(self, gid: int) -> None:
        with self._lock:
            self._lost.add(gid)

    def on_map_reset(self) -> None:
        with self._lock:
            self._map_reset = True

    def drain(self) -> TickEvents:
        with self._lock:
            died = frozenset(self._died)
            lost = frozenset(self._lost)
            map_reset = self._map_reset
            self._died.clear()
            self._lost.clear()
            self._map_reset = False
        return TickEvents(
            died_gids=died, lost_gids=lost, map_reset=map_reset,
        )
