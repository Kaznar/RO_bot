"""Packet sniffer — captures RO server → client TCP traffic with scapy
and maintains live caches of entities and player state.

Responsibilities:
  * Auto-detect the RO server IP from the client process's ESTABLISHED
    TCP connections (netstat).
  * Parse the plaintext opcodes we care about (delegated to
    :mod:`ro_bot.core.network.parser`).
  * Maintain `EntityState` dict keyed by GID, cache player state.
  * Dispatch events (spawn / vanish / map_change) to registered
    callbacks and listeners. Callbacks run on the sniffer thread; keep
    them fast and exception-safe.

Requires Npcap on Windows.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from ro_bot.core.network.packets import (
    PacketConfig,
    SP_HP,
    SP_MAXHP,
    VanishType,
)
from ro_bot.core.network.parser import (
    PacketParser,
    iter_map_change,
    iter_player_move,
    iter_status_change,
    iter_status_change_long,
    iter_stopmove,
    iter_vanish,
)

logger = logging.getLogger(__name__)

# How long an entity can go without an update before we treat it as
# gone. 30 s comfortably covers walk cycles and visibility lapses;
# anything longer is either a zone transition we missed or a stuck slot.
ENTITY_STALE_TIMEOUT = 30.0

_SNAPPROCESS = 0x00000002


@dataclass
class EntityState:
    """Live state of a tracked entity. Mutable — the sniffer thread
    updates fields in place under ``PacketSniffer._lock``.
    """
    gid: int
    name: str
    x: int = 0
    y: int = 0
    hp: int = 0
    max_hp: int = 0
    last_seen: float = 0.0


@dataclass
class _PlayerPos:
    x: int = 0
    y: int = 0


def _find_ro_pid(process_name: str) -> int | None:
    """Find PID by exe-stem substring. Used to filter netstat output."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _E(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.wintypes.DWORD),
            ("cntUsage", ctypes.wintypes.DWORD),
            ("th32ProcessID", ctypes.wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", ctypes.wintypes.DWORD),
            ("cntThreads", ctypes.wintypes.DWORD),
            ("th32ParentProcessID", ctypes.wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", ctypes.wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    needle = process_name.lower().removesuffix(".exe")
    snap = kernel32.CreateToolhelp32Snapshot(_SNAPPROCESS, 0)
    if snap == -1:
        return None
    entry = _E()
    entry.dwSize = ctypes.sizeof(_E)
    try:
        if not kernel32.Process32First(snap, ctypes.byref(entry)):
            return None
        while True:
            exe = entry.szExeFile.decode("utf-8", errors="replace").lower()
            if needle in exe:
                return int(entry.th32ProcessID)
            if not kernel32.Process32Next(snap, ctypes.byref(entry)):
                return None
    finally:
        kernel32.CloseHandle(snap)


def find_server_host(process_name: str) -> str | None:
    """Auto-detect RO server IP from the client's ESTABLISHED TCP sockets."""
    ro_pid = _find_ro_pid(process_name)
    if ro_pid is None:
        return None
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None

    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[-1] != str(ro_pid):
            continue
        if "ESTABLISHED" not in parts[3]:
            continue
        foreign = parts[2]
        if ":" not in foreign:
            continue
        host = foreign.rsplit(":", 1)[0]
        if host.startswith("["):
            host = host[1:-1]
        if not host.startswith("127."):
            logger.info("Detected server: %s (PID=%d)", host, ro_pid)
            return host
    return None


class PacketSniffer:
    """Scapy-based TCP sniffer on a background thread.

    Public surface is split into three groups:

      * lifecycle: ``connect`` / ``disconnect`` / ``is_connected``
      * queries: ``get_player_pos``, ``get_player_hp``, ``get_map_name``,
        ``get_entity``, ``get_all_entities``, ``is_entity_alive``
      * events: ``add_entity_vanish_listener`` / ``add_map_change_listener``
        (plus single-slot callbacks for :class:`EntityTracker`)
    """

    def __init__(
        self,
        process_name: str,
        packet_config: PacketConfig | None = None,
        server_host: str | None = None,
    ) -> None:
        self._process_name = process_name
        self._pkt_cfg = packet_config or PacketConfig()
        self._parser = PacketParser(self._pkt_cfg)
        self._server_host = server_host

        self._entities: dict[int, EntityState] = {}
        self._lock = threading.Lock()
        self._recently_dead: dict[int, float] = {}

        self._player = _PlayerPos()
        self._player_gid: int = 0
        self._char_name: str = ""
        self._player_hp: int = 0
        self._player_hp_max: int = 0
        self._player_lock = threading.Lock()
        self._map_name: str | None = None

        # Diagnostic: every distinct sp_type seen on 0x00B0 / 0x0ACB.
        # Used by HealPolicy to expose why hp_max stays at 0 (e.g. server
        # never sent SP_MAXHP=6 because login predates the sniffer).
        self._sp_types_seen: set[int] = set()

        self._sniff_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._connected = False

        # Single-slot callbacks owned by EntityTracker.
        self._entity_spawn_cb: Callable[[int, str], None] | None = None
        self._entity_vanish_cb: Callable[[int, int], None] | None = None
        self._map_change_cb: Callable[[str, int, int], None] | None = None

        # Additional listeners for hunt policies (coexist with tracker).
        self._vanish_listeners: list[Callable[[int, int], None]] = []
        self._map_listeners: list[Callable[[str, int, int], None]] = []

    # ── Configuration ───────────────────────────────────────────────

    def set_char_name(self, name: str) -> None:
        """Set the local player's character name.

        Used to recognize which 0x0A30 identifies *us* (to capture our
        GID and filter our own entity entry out of ``get_all_entities``).
        """
        self._char_name = name

    def set_entity_spawn_callback(
        self, cb: Callable[[int, str], None] | None,
    ) -> None:
        self._entity_spawn_cb = cb

    def set_entity_vanish_callback(
        self, cb: Callable[[int, int], None] | None,
    ) -> None:
        self._entity_vanish_cb = cb

    def set_map_change_callback(
        self, cb: Callable[[str, int, int], None] | None,
    ) -> None:
        self._map_change_cb = cb

    def add_entity_vanish_listener(
        self, cb: Callable[[int, int], None],
    ) -> None:
        self._vanish_listeners.append(cb)

    def remove_entity_vanish_listener(
        self, cb: Callable[[int, int], None],
    ) -> None:
        try:
            self._vanish_listeners.remove(cb)
        except ValueError:
            pass

    def add_map_change_listener(
        self, cb: Callable[[str, int, int], None],
    ) -> None:
        self._map_listeners.append(cb)

    def remove_map_change_listener(
        self, cb: Callable[[str, int, int], None],
    ) -> None:
        try:
            self._map_listeners.remove(cb)
        except ValueError:
            pass

    # ── Lifecycle ───────────────────────────────────────────────────

    def connect(self, wait_timeout: float = 120.0) -> bool:
        """Start the sniffer thread. Auto-detects server IP if not set."""
        if self._connected:
            return True

        if not self._server_host:
            if not self._resolve_server_host(wait_timeout):
                return False

        self._stop_event.clear()
        self._sniff_thread = threading.Thread(
            target=self._sniff_loop, daemon=True, name="packet-sniffer",
        )
        self._sniff_thread.start()
        self._connected = True
        logger.info("PacketSniffer started: host=%s", self._server_host)
        return True

    def _resolve_server_host(self, wait_timeout: float) -> bool:
        deadline = time.monotonic() + wait_timeout
        logger.info(
            "Waiting for %s server connection (%.0fs timeout)...",
            self._process_name, wait_timeout,
        )
        while time.monotonic() < deadline:
            host = find_server_host(self._process_name)
            if host is not None:
                self._server_host = host
                return True
            time.sleep(3.0)
        logger.error("Cannot detect RO server within %.0fs", wait_timeout)
        return False

    def disconnect(self) -> None:
        self._stop_event.set()
        if self._sniff_thread and self._sniff_thread.is_alive():
            self._sniff_thread.join(timeout=5.0)
        self._connected = False
        self._sniff_thread = None
        with self._lock:
            self._entities.clear()
        logger.info("PacketSniffer stopped")

    @property
    def is_connected(self) -> bool:
        return (
            self._connected
            and self._sniff_thread is not None
            and self._sniff_thread.is_alive()
        )

    # ── Queries ─────────────────────────────────────────────────────

    def get_map_name(self) -> str | None:
        return self._map_name

    def get_player_pos(self) -> tuple[int, int]:
        with self._player_lock:
            return self._player.x, self._player.y

    def get_player_hp(self) -> tuple[int, int]:
        """(hp, hp_max) from 0x00B0 cache. Both 0 until first HP packet."""
        with self._player_lock:
            return self._player_hp, self._player_hp_max

    def get_sp_types_seen(self) -> frozenset[int]:
        """Snapshot of every distinct sp_type observed on 0x00B0 / 0x0ACB.

        Diagnostic hook for the heal policy: if SP_MAXHP (=6) is never
        in this set, the server simply hasn't sent it on the captured
        TCP stream (typical when the sniffer connects after login).
        """
        with self._player_lock:
            return frozenset(self._sp_types_seen)

    def get_player_gid(self) -> int:
        return self._player_gid

    def get_entity(self, gid: int) -> EntityState | None:
        now = time.monotonic()
        with self._lock:
            ent = self._entities.get(gid)
            if ent is None or now - ent.last_seen > ENTITY_STALE_TIMEOUT:
                return None
            return _clone(ent)

    def get_all_entities(self) -> list[EntityState]:
        """Snapshots of all fresh entities, excluding the local player."""
        now = time.monotonic()
        with self._lock:
            return [
                _clone(e)
                for e in self._entities.values()
                if now - e.last_seen <= ENTITY_STALE_TIMEOUT
                and e.name
                and e.gid != self._player_gid
            ]

    def is_entity_alive(self, gid: int) -> bool:
        with self._lock:
            ent = self._entities.get(gid)
            if ent is None:
                return False
            return not (ent.max_hp > 0 and ent.hp <= 0)

    # ── Sniffer thread ──────────────────────────────────────────────

    def _sniff_loop(self) -> None:
        from scapy.all import IP, TCP, sniff

        bpf = f"tcp and host {self._server_host}"
        logger.debug("Sniff BPF: %s", bpf)

        def process(pkt):
            if self._stop_event.is_set():
                return
            if not pkt.haslayer(TCP) or not pkt.haslayer(IP):
                return
            if pkt[IP].src != self._server_host:
                return
            payload = bytes(pkt[TCP].payload)
            if payload:
                self._dispatch(payload)

        try:
            sniff(
                filter=bpf, prn=process,
                stop_filter=lambda _: self._stop_event.is_set(),
                store=False,
            )
        except Exception as e:
            logger.error("Sniff thread error: %s", e)

    def _dispatch(self, payload: bytes) -> None:
        for ent in self._parser.scan_for_entities(payload):
            self._on_entity_name_hp(ent.gid, ent.name, ent.hp, ent.max_hp)
        for move in iter_player_move(payload, self._pkt_cfg):
            self._on_player_move(move.to_x, move.to_y)
        for v in iter_vanish(payload, self._pkt_cfg):
            self._on_vanish(v.gid, v.vanish_type)
        for gid, x, y in iter_stopmove(payload, self._pkt_cfg):
            self._on_stopmove(gid, x, y)
        for m in iter_map_change(payload, self._pkt_cfg):
            self._on_map_change(m.map_name, m.x, m.y)
        for s in iter_status_change(payload, self._pkt_cfg):
            self._on_status_change(s.type, s.value)
        for s in iter_status_change_long(payload, self._pkt_cfg):
            self._on_status_change(s.type, s.value)

    # ── Event handlers ──────────────────────────────────────────────

    def _on_entity_name_hp(
        self, gid: int, name: str, hp: int, max_hp: int,
    ) -> None:
        now = time.monotonic()

        if self._char_name and name == self._char_name:
            self._player_gid = gid
            with self._lock:
                self._entities.pop(gid, None)
            return

        # Skip post-mortem 0x0A30 re-announcements (server sends them
        # briefly after death for corpse display).
        dead_time = self._recently_dead.get(gid)
        if dead_time is not None and now - dead_time < 5.0:
            return

        is_first_sight = False
        with self._lock:
            ent = self._entities.get(gid)
            if ent is None:
                self._entities[gid] = EntityState(
                    gid=gid, name=name, hp=hp, max_hp=max_hp, last_seen=now,
                )
                is_first_sight = True
            else:
                ent.name, ent.hp, ent.max_hp, ent.last_seen = (
                    name, hp, max_hp, now,
                )

        if is_first_sight:
            logger.info(
                "Entity: GID=%d name='%s' HP=%d/%d", gid, name, hp, max_hp,
            )
            _safe_call(self._entity_spawn_cb, gid, name)

    def _on_vanish(self, gid: int, vanish_type: int) -> None:
        with self._lock:
            removed = self._entities.pop(gid, None)
            if removed and vanish_type == VanishType.DIED:
                self._recently_dead[gid] = time.monotonic()
        if not (removed and removed.name):
            return
        reason = "died" if vanish_type == VanishType.DIED else f"type={vanish_type}"
        logger.info(
            "Entity vanish: GID=%d name='%s' (%s)",
            gid, removed.name, reason,
        )
        _safe_call(self._entity_vanish_cb, gid, vanish_type)
        for lst in self._vanish_listeners:
            _safe_call(lst, gid, vanish_type)

    def _on_player_move(self, to_x: int, to_y: int) -> None:
        with self._player_lock:
            self._player.x = to_x
            self._player.y = to_y
        logger.info("Player move: ->(%d,%d)", to_x, to_y)

    def _on_map_change(self, map_name: str, x: int, y: int) -> None:
        logger.info("Map change: %s (%d,%d)", map_name, x, y)
        self._map_name = map_name
        with self._player_lock:
            self._player.x = x
            self._player.y = y
        with self._lock:
            self._entities.clear()
        _safe_call(self._map_change_cb, map_name, x, y)
        for lst in self._map_listeners:
            _safe_call(lst, map_name, x, y)

    def _on_status_change(self, sp_type: int, value: int) -> None:
        first_max = False
        with self._player_lock:
            is_first = sp_type not in self._sp_types_seen
            self._sp_types_seen.add(sp_type)
            if sp_type == SP_HP:
                self._player_hp = value
            elif sp_type == SP_MAXHP:
                first_max = self._player_hp_max == 0 and value > 0
                self._player_hp_max = value
        # Log outside the lock; first-ever MAXHP is the milestone that
        # unblocks healing, so surface it loudly.
        if first_max:
            logger.info("First SP_MAXHP received: max_hp=%d", value)
        elif is_first:
            logger.debug(
                "First sighting sp_type=%d value=%d", sp_type, value,
            )

    def _on_stopmove(self, gid: int, x: int, y: int) -> None:
        if gid == self._player_gid:
            return
        now = time.monotonic()
        with self._lock:
            ent = self._entities.get(gid)
            if ent is None:
                self._entities[gid] = EntityState(
                    gid=gid, name="", x=x, y=y, last_seen=now,
                )
                logger.info("Entity stop: GID=%d pos=(%d,%d)", gid, x, y)
            else:
                ent.x, ent.y, ent.last_seen = x, y, now


def _clone(ent: EntityState) -> EntityState:
    return EntityState(
        gid=ent.gid, name=ent.name, x=ent.x, y=ent.y,
        hp=ent.hp, max_hp=ent.max_hp, last_seen=ent.last_seen,
    )


def _safe_call(cb: Callable | None, *args) -> None:
    if cb is None:
        return
    try:
        cb(*args)
    except Exception:
        logger.exception("sniffer callback raised")
