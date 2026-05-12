"""Live `(GID → memory-struct-address)` cache backed by the sniffer.

This module glues the network layer (``PacketSniffer``) to the process
memory layer (``core.memory.entity_scanner``) so the bot can ask:

    tracker.get_position(gid) → (x, y) | None

without doing a memory scan in the request path. Scans happen in a
background worker thread; pending spawns are drained greedily so a
single heap pass resolves the whole burst at once.

Three threads cooperate:

  * **Sniffer thread** — detects spawn / vanish / map_change. Callbacks
    queue spawns (after the optional ``should_track`` filter), drop
    cache on vanish, clear cache + start grace window on map_change.
  * **Scanner thread** — coalesces queued spawns into a batch and runs
    one ~1 s ``find_entity_addrs_batch`` scan that resolves every GID
    in a single heap pass. Without batching, a 5-mob teleport burst
    would take ~6.5 s before all positions were known.
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
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from ro_bot.core.memory.entity_scanner import (
    find_entity_addrs_batch,
    read_entity_pos,
)
from ro_bot.core.memory.offsets import MAP_COORD_MAX, MAP_COORD_MIN
from ro_bot.core.memory.process import ProcessHandle
from ro_bot.core.network.sniffer import PacketSniffer

logger = logging.getLogger(__name__)

# Empirically the torn-write window after 0x0091 is ~200 ms; 500 ms is
# a safe margin without being noticeable in the bot's reaction time.
MAP_CHANGE_GRACE_SEC = 0.5

# Upper bound on pending spawns. Dropped only if the player sprints
# through dozens of mobs faster than the scanner can resolve them.
SPAWN_QUEUE_MAX = 256

# Padding around observed entity addresses for the adaptive scan
# window. RO allocates entity structs in a slab — the live set spans
# only a few MB even on a busy map. ±2 MB gives us headroom for slot
# recycling and slab growth while still reducing the scan range from
# the full 2 GB heap to ~4 MB (≈500× fewer chunks to walk).
SCAN_RANGE_PADDING = 0x200000

# Idle poll while the spawn queue is empty.
SCANNER_QUEUE_POLL_SEC = 0.05


@dataclass
class _Entry:
    """Resolved entity cache row."""
    gid_addr: int
    name: str


def _valid_map_cell(x: int, y: int) -> bool:
    return MAP_COORD_MIN <= x <= MAP_COORD_MAX and MAP_COORD_MIN <= y <= MAP_COORD_MAX


class EntityTracker:
    """Subscribes to a sniffer and maintains a (gid → struct addr) map."""

    def __init__(
        self,
        process: ProcessHandle,
        sniffer: PacketSniffer,
        should_track: Callable[[int, str], bool] | None = None,
    ) -> None:
        self._process = process
        self._sniffer = sniffer
        # Optional pre-queue filter. Called on the sniffer thread, so it
        # must be cheap and thread-safe (typical use: closure over an
        # immutable frozenset of allowed names). When None, every spawn
        # is queued for memory resolution.
        self._should_track = should_track

        self._cache: dict[int, _Entry] = {}
        self._lock = threading.Lock()

        self._spawn_q: queue.Queue[tuple[int, str]] = queue.Queue(
            maxsize=SPAWN_QUEUE_MAX,
        )
        self._scanner: threading.Thread | None = None
        self._stop = threading.Event()

        # Wall clock until which all reads return None.
        self._invalidate_until: float = 0.0

        # Adaptive scan window — None on cold start, then learned from
        # successful resolves. Owned and mutated by the scanner thread
        # only; no lock needed. Persists across map changes (the entity
        # slab in process memory does not move when the map switches).
        self._scan_range: tuple[int, int] | None = None

        # Stats.
        self._scans_ok: int = 0
        self._scans_failed: int = 0
        self._dropped_spawns: int = 0
        self._filtered_spawns: int = 0
        self._queued_resolve: set[int] = set()

    def _should_track_entity(self, gid: int, name: str) -> bool:
        if self._should_track is None:
            return True
        return self._should_track(gid, name)

    def _enqueue_resolve(self, gid: int, name: str) -> None:
        if not self._should_track_entity(gid, name):
            return
        with self._lock:
            if gid in self._cache or gid in self._queued_resolve:
                return
            self._queued_resolve.add(gid)
        try:
            self._spawn_q.put_nowait((gid, name))
        except queue.Full:
            self._dropped_spawns += 1
            with self._lock:
                self._queued_resolve.discard(gid)
            try:
                self._spawn_q.get_nowait()
                self._spawn_q.put_nowait((gid, name))
                with self._lock:
                    self._queued_resolve.add(gid)
            except (queue.Empty, queue.Full):
                pass

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        if self._scanner is not None and self._scanner.is_alive():
            return
        self._stop.clear()
        self._sniffer.set_entity_spawn_callback(self._on_spawn)
        self._sniffer.set_entity_vanish_callback(self._on_vanish)
        self._sniffer.set_map_change_callback(self._on_map_change)
        self._sniffer.add_entity_stopmove_listener(self._on_stopmove_packet)
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
        self._sniffer.remove_entity_stopmove_listener(self._on_stopmove_packet)
        if self._scanner is not None and self._scanner.is_alive():
            self._scanner.join(timeout=2.0)
        self._scanner = None
        logger.info(
            "EntityTracker stopped (scans ok=%d failed=%d dropped=%d "
            "filtered=%d)",
            self._scans_ok, self._scans_failed, self._dropped_spawns,
            self._filtered_spawns,
        )

    # ── Public API (caller thread) ───────────────────────────────────

    def get_position(self, gid: int) -> tuple[int, int] | None:
        if time.monotonic() < self._invalidate_until:
            return None
        with self._lock:
            entry = self._cache.get(gid)
        if entry is not None:
            pos = read_entity_pos(self._process, entry.gid_addr, gid)
            if pos is not None:
                return pos
            with self._lock:
                self._cache.pop(gid, None)
        return self._sniffer_packet_position(gid)

    def _sniffer_packet_position(self, gid: int) -> tuple[int, int] | None:
        ent = self._sniffer.get_entity(gid)
        if ent is None or not ent.name:
            return None
        if not _valid_map_cell(ent.x, ent.y):
            return None
        return (ent.x, ent.y)

    def get_all_positions(self) -> list[tuple[int, str, int, int]]:
        """Snapshot of ``[(gid, name, x, y), ...]`` for tracked entities.

        Memory-resolved slots are preferred; plaintext ``0x0088`` cells from
        the sniffer fill the gap until the heap scan catches up.
        """
        if time.monotonic() < self._invalidate_until:
            return []
        with self._lock:
            snapshot = list(self._cache.items())

        resolved: dict[int, tuple[str, int, int]] = {}
        recycled: list[int] = []
        for gid, entry in snapshot:
            pos = read_entity_pos(self._process, entry.gid_addr, gid)
            if pos is None:
                recycled.append(gid)
                continue
            resolved[gid] = (entry.name, pos[0], pos[1])

        if recycled:
            with self._lock:
                for gid in recycled:
                    self._cache.pop(gid, None)
                    self._queued_resolve.discard(gid)

        for ent in self._sniffer.get_all_entities():
            if not ent.name or not self._should_track_entity(ent.gid, ent.name):
                continue
            if ent.gid in resolved:
                continue
            if not _valid_map_cell(ent.x, ent.y):
                self._enqueue_resolve(ent.gid, ent.name)
                continue
            resolved[ent.gid] = (ent.name, ent.x, ent.y)
            self._enqueue_resolve(ent.gid, ent.name)

        return [
            (gid, name, x, y)
            for gid, (name, x, y) in resolved.items()
        ]

    def get_awaiting_position_entities(self) -> list[tuple[int, str]]:
        """Tracked sniffer entities that have a name but no cell yet."""
        if time.monotonic() < self._invalidate_until:
            return []
        out: list[tuple[int, str]] = []
        for ent in self._sniffer.get_all_entities():
            if not ent.name or not self._should_track_entity(ent.gid, ent.name):
                continue
            if _valid_map_cell(ent.x, ent.y):
                continue
            out.append((ent.gid, ent.name))
        return out

    def cache_size(self) -> int:
        with self._lock:
            return len(self._cache)

    # ── Sniffer callbacks (sniffer thread — must be quick) ──────────

    def _on_spawn(self, gid: int, name: str) -> None:
        if not self._should_track_entity(gid, name):
            self._filtered_spawns += 1
            return
        self._enqueue_resolve(gid, name)

    def _on_stopmove_packet(self, gid: int, x: int, y: int) -> None:
        if time.monotonic() < self._invalidate_until:
            return
        if not _valid_map_cell(x, y):
            return
        ent = self._sniffer.get_entity(gid)
        if ent is None or not ent.name:
            return
        self._enqueue_resolve(gid, ent.name)

    def _on_vanish(self, gid: int, _vanish_type: int) -> None:
        with self._lock:
            self._cache.pop(gid, None)
            self._queued_resolve.discard(gid)

    def _on_map_change(self, _map: str, _x: int, _y: int) -> None:
        self._invalidate_until = time.monotonic() + MAP_CHANGE_GRACE_SEC
        with self._lock:
            self._cache.clear()
            self._queued_resolve.clear()
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
                first = self._spawn_q.get(timeout=SCANNER_QUEUE_POLL_SEC)
            except queue.Empty:
                continue
            # Greedy drain: coalesce everything else queued in the
            # meantime. A teleport burst arrives in tens of ms, so this
            # almost always picks up the whole burst on first wake.
            batch: list[tuple[int, str]] = [first]
            while True:
                try:
                    batch.append(self._spawn_q.get_nowait())
                except queue.Empty:
                    break
            self._try_resolve_batch(batch)

    def _try_resolve_batch(self, batch: list[tuple[int, str]]) -> None:
        # Honor map-change grace: requeue and back off briefly.
        grace_left = self._invalidate_until - time.monotonic()
        if grace_left > 0:
            for item in batch:
                try:
                    self._spawn_q.put_nowait(item)
                except queue.Full:
                    pass
            time.sleep(min(grace_left, 0.2))
            return

        # Skip GIDs already cached (e.g. resolved by a previous batch
        # whose scan was already in flight when the spawn was queued).
        name_by_gid: dict[int, str] = {}
        with self._lock:
            for gid, name in batch:
                if gid not in self._cache:
                    name_by_gid[gid] = name
        if not name_by_gid:
            return

        gids = list(name_by_gid)
        hint = self._scan_range

        # Narrow scan first — a few MB walk instead of 2 GB once we
        # know where the entity slab lives. Cold start (no hint) skips
        # straight to the full scan.
        t0 = time.monotonic()
        addrs: dict[int, int] = {}
        if hint is not None:
            addrs = find_entity_addrs_batch(
                self._process, gids, range_hint=hint,
            )

        # Fallback: any GID the narrow window missed (or every GID on
        # cold start) gets a full-heap scan. This is also how the
        # window self-heals when the slab grows beyond the learned
        # bounds.
        missing = [g for g in gids if g not in addrs]
        used_fallback = bool(missing)
        if missing:
            full_addrs = find_entity_addrs_batch(
                self._process, missing, range_hint=None,
            )
            addrs.update(full_addrs)
        dt = time.monotonic() - t0

        if addrs:
            self._update_scan_range(addrs.values())
            with self._lock:
                for gid, addr in addrs.items():
                    self._cache[gid] = _Entry(
                        gid_addr=addr, name=name_by_gid[gid],
                    )
                    self._queued_resolve.discard(gid)

        n = len(name_by_gid)
        scope = (
            "full" if hint is None
            else ("narrow+full" if used_fallback else "narrow")
        )
        for gid, name in name_by_gid.items():
            addr = addrs.get(gid)
            if addr is not None:
                self._scans_ok += 1
                logger.debug(
                    "Scanner: GID=%d '%s' resolved at 0x%08X "
                    "(batch=%d, scope=%s, %.2fs)",
                    gid, name, addr, n, scope, dt,
                )
            else:
                self._scans_failed += 1
                with self._lock:
                    self._queued_resolve.discard(gid)
                logger.debug(
                    "Scanner: GID=%d '%s' not found "
                    "(batch=%d, scope=%s, %.2fs)",
                    gid, name, n, scope, dt,
                )

    def _update_scan_range(self, addresses: Iterable[int]) -> None:
        """Learn / widen the scan window from a freshly resolved batch.

        Called only from the scanner thread, so no lock is needed for
        ``_scan_range``. Window only widens — slab regions don't move
        in process memory once allocated.
        """
        observed_lo = min(addresses)
        observed_hi = max(addresses)
        new_lo = max(0, observed_lo - SCAN_RANGE_PADDING)
        new_hi = observed_hi + SCAN_RANGE_PADDING
        old = self._scan_range
        if old is None:
            self._scan_range = (new_lo, new_hi)
            mb = (new_hi - new_lo) / (1024 * 1024)
            logger.info(
                "Scan range learned: 0x%08X-0x%08X (window=%.0fMB)",
                new_lo, new_hi, mb,
            )
            return
        old_lo, old_hi = old
        merged_lo = min(old_lo, new_lo)
        merged_hi = max(old_hi, new_hi)
        if (merged_lo, merged_hi) != (old_lo, old_hi):
            self._scan_range = (merged_lo, merged_hi)
            mb = (merged_hi - merged_lo) / (1024 * 1024)
            logger.info(
                "Scan range widened: 0x%08X-0x%08X (window=%.0fMB)",
                merged_lo, merged_hi, mb,
            )
