"""Live `(GID → memory-struct-address)` cache backed by the sniffer.

This module glues the network layer (``PacketSniffer``) to the process
memory layer (``core.memory.entity_scanner``) so the bot can ask:

    tracker.get_position(gid) → (x, y) | None

without doing a memory scan in the request path. Scans happen in a
background worker thread, one GID at a time.

Three threads cooperate:

  * **Sniffer thread** — detects spawn / vanish / map_change. Callbacks
    queue spawns, drop cache on vanish, clear cache + start grace
    window on map_change.
  * **Scanner thread** — consumes the spawn queue, runs the ~1 s
    ``find_entity_addr`` scan, writes the result into the cache.
  * **Caller thread** — reads ``get_position`` / ``get_all_positions``.
    One 100-byte ``ReadProcessMemory`` with defense against recycled
    slots and torn writes.

Map change handling: after a map change we set ``_invalidate_until``
to ``now + MAP_CHANGE_GRACE_SEC``; reads return empty until then.
This covers the ~200 ms window where the engine re-populates the
player struct with two non-atomic int32 stores and we'd otherwise
see torn values.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass

from ro_bot.core.memory.entity_scanner import find_entity_addr, read_entity_pos
from ro_bot.core.memory.process import ProcessHandle
from ro_bot.core.network.sniffer import PacketSniffer

logger = logging.getLogger(__name__)

# Empirically the torn-write window after 0x0091 is ~200 ms; 500 ms is
# a safe margin without being noticeable in the bot's reaction time.
MAP_CHANGE_GRACE_SEC = 0.5

# Upper bound on pending spawns. Dropped only if the player sprints
# through dozens of mobs faster than the scanner can resolve them.
SPAWN_QUEUE_MAX = 256


@dataclass
class _Entry:
    """Resolved entity cache row."""
    gid_addr: int
    name: str


class EntityTracker:
    """Subscribes to a sniffer and maintains a (gid → struct addr) map."""

    def __init__(
        self,
        process: ProcessHandle,
        sniffer: PacketSniffer,
    ) -> None:
        self._process = process
        self._sniffer = sniffer

        self._cache: dict[int, _Entry] = {}
        self._lock = threading.Lock()

        self._spawn_q: queue.Queue[tuple[int, str]] = queue.Queue(
            maxsize=SPAWN_QUEUE_MAX,
        )
        self._scanner: threading.Thread | None = None
        self._stop = threading.Event()

        # Wall clock until which all reads return None.
        self._invalidate_until: float = 0.0

        # Stats.
        self._scans_ok: int = 0
        self._scans_failed: int = 0
        self._dropped_spawns: int = 0

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        if self._scanner is not None and self._scanner.is_alive():
            return
        self._stop.clear()
        self._sniffer.set_entity_spawn_callback(self._on_spawn)
        self._sniffer.set_entity_vanish_callback(self._on_vanish)
        self._sniffer.set_map_change_callback(self._on_map_change)
        self._scanner = threading.Thread(
            target=self._scanner_loop, daemon=True, name="entity-tracker-scan",
        )
        self._scanner.start()
        logger.info("EntityTracker started")

    def stop(self) -> None:
        self._stop.set()
        self._sniffer.set_entity_spawn_callback(None)
        self._sniffer.set_entity_vanish_callback(None)
        self._sniffer.set_map_change_callback(None)
        if self._scanner is not None and self._scanner.is_alive():
            self._scanner.join(timeout=2.0)
        self._scanner = None
        logger.info(
            "EntityTracker stopped (scans ok=%d failed=%d dropped=%d)",
            self._scans_ok, self._scans_failed, self._dropped_spawns,
        )

    # ── Public API (caller thread) ───────────────────────────────────

    def get_position(self, gid: int) -> tuple[int, int] | None:
        if time.monotonic() < self._invalidate_until:
            return None
        with self._lock:
            entry = self._cache.get(gid)
        if entry is None:
            return None
        pos = read_entity_pos(self._process, entry.gid_addr, gid)
        if pos is None:
            # Slot was recycled; drop so we re-resolve on next spawn.
            with self._lock:
                self._cache.pop(gid, None)
            return None
        return pos

    def get_all_positions(self) -> list[tuple[int, str, int, int]]:
        """Snapshot of ``[(gid, name, x, y), ...]`` for every resolved
        entity whose slot is still readable. Recycled slots are purged
        from the cache as a side-effect.
        """
        if time.monotonic() < self._invalidate_until:
            return []
        with self._lock:
            snapshot = list(self._cache.items())

        out: list[tuple[int, str, int, int]] = []
        recycled: list[int] = []
        for gid, entry in snapshot:
            pos = read_entity_pos(self._process, entry.gid_addr, gid)
            if pos is None:
                recycled.append(gid)
                continue
            out.append((gid, entry.name, pos[0], pos[1]))

        if recycled:
            with self._lock:
                for gid in recycled:
                    self._cache.pop(gid, None)
        return out

    def cache_size(self) -> int:
        with self._lock:
            return len(self._cache)

    # ── Sniffer callbacks (sniffer thread — must be quick) ──────────

    def _on_spawn(self, gid: int, name: str) -> None:
        try:
            self._spawn_q.put_nowait((gid, name))
        except queue.Full:
            self._dropped_spawns += 1
            # Drop oldest, retry. Acceptable for a passive tracker.
            try:
                self._spawn_q.get_nowait()
                self._spawn_q.put_nowait((gid, name))
            except (queue.Empty, queue.Full):
                pass

    def _on_vanish(self, gid: int, _vanish_type: int) -> None:
        with self._lock:
            self._cache.pop(gid, None)

    def _on_map_change(self, _map: str, _x: int, _y: int) -> None:
        self._invalidate_until = time.monotonic() + MAP_CHANGE_GRACE_SEC
        with self._lock:
            self._cache.clear()
        # Drop pending spawns from the previous map; engine will re-emit.
        while True:
            try:
                self._spawn_q.get_nowait()
            except queue.Empty:
                break

    # ── Scanner thread ──────────────────────────────────────────────

    def _scanner_loop(self) -> None:
        while not self._stop.is_set():
            try:
                gid, name = self._spawn_q.get(timeout=0.5)
            except queue.Empty:
                continue
            self._try_resolve(gid, name)

    def _try_resolve(self, gid: int, name: str) -> None:
        # Honor map-change grace: requeue + short sleep.
        grace_left = self._invalidate_until - time.monotonic()
        if grace_left > 0:
            try:
                self._spawn_q.put_nowait((gid, name))
            except queue.Full:
                pass
            time.sleep(min(grace_left, 0.2))
            return

        with self._lock:
            if gid in self._cache:
                return

        t0 = time.monotonic()
        addr = find_entity_addr(self._process, gid)
        dt = time.monotonic() - t0

        if addr is None:
            self._scans_failed += 1
            logger.debug(
                "Scanner: GID=%d '%s' not found (%.2fs)", gid, name, dt,
            )
            return

        with self._lock:
            self._cache[gid] = _Entry(gid_addr=addr, name=name)
        self._scans_ok += 1
        logger.debug(
            "Scanner: GID=%d '%s' resolved at 0x%08X (%.2fs)",
            gid, name, addr, dt,
        )
