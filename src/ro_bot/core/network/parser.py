"""Packet parsing — pure decoders, no state.

Two flavors of parser:

* :class:`PacketParser` for 0x0A30 (name + HP) because it needs regex
  matching on variable-length payload.
* Module-level ``iter_*`` generators for the marker-scan packets
  (0x0080, 0x0087, 0x0088, 0x0091, 0x00B0, 0x0ACB). Each walks the raw
  payload, locates valid occurrences of its marker, and yields typed
  events.

Keeping these separate from the sniffer keeps the sniffer focused on
state + dispatch and keeps file sizes sane.
"""

from __future__ import annotations

import logging
import struct
from collections.abc import Iterator

from ro_bot.core.network.entity_name_parser import scan_entity_name_packets
from ro_bot.core.network.packets import (
    EntityVanish,
    MapChange,
    PacketConfig,
    PlayerMovePos,
    StatusChange,
)

logger = logging.getLogger(__name__)


# ── Diagnostic probes (temporary) ────────────────────────────────────
#
# Per-opcode counters that cap how many raw packet dumps reach the log
# when a parser can't extract what it expects. Pure telemetry — remove
# once the NexusRO / Gepard packet variants are mapped.

_PROBE_LIMIT_DEFAULT = 10
# Status-change opcodes need a wider window: SP_MAXHP arrives only once
# (or rarely) and may sit deeper in the stream than the first 10 hits.
_PROBE_LIMITS: dict[str, int] = {
    "0x00B0": 50,
    "0x0ACB": 50,
}
_probe_counts: dict[str, int] = {}


def _probe(tag: str) -> bool:
    """Return True up to the per-tag probe limit, then False."""
    limit = _PROBE_LIMITS.get(tag, _PROBE_LIMIT_DEFAULT)
    n = _probe_counts.get(tag, 0)
    if n >= limit:
        return False
    _probe_counts[tag] = n + 1
    return True


def _hex_window(data: bytes, idx: int, before: int = 4, after: int = 32) -> str:
    lo = max(0, idx - before)
    hi = min(len(data), idx + after)
    return data[lo:hi].hex(" ")


# ── 0x0087 ZC_NOTIFY_PLAYERMOVE helpers ──────────────────────────────

def decode_pos2(data: bytes, offset: int = 0) -> tuple[int, int, int, int]:
    """Decode rAthena's 6-byte RBUFPOS2 (from → to cell coordinates)."""
    b = data[offset:offset + 6]
    from_x = (b[0] << 2) | (b[1] >> 6)
    from_y = ((b[1] & 0x3F) << 4) | (b[2] >> 4)
    to_x = ((b[2] & 0x0F) << 6) | (b[3] >> 2)
    to_y = ((b[3] & 0x03) << 8) | b[4]
    return from_x, from_y, to_x, to_y


def _read_name(data: bytes, offset: int, max_len: int = 24) -> str:
    end = min(offset + max_len, len(data))
    chunk = data[offset:end]
    null_pos = chunk.find(b"\x00")
    if null_pos >= 0:
        chunk = chunk[:null_pos]
    return chunk.decode("utf-8", errors="replace")


class PacketParser:
    """Scans entity name / HP opcodes in a TCP payload (see entity_name_parser)."""

    def __init__(self, config: PacketConfig | None = None) -> None:
        self._cfg = config or PacketConfig()

    def scan_for_entities(self, data: bytes):
        return scan_entity_name_packets(data, self._cfg)


# ── Marker-scan iterators ────────────────────────────────────────────
#
# Each iterator walks `data`, locates valid (plausible) packet
# occurrences, and yields a typed event. Invalid hits (out-of-range
# coords, torn bytes) are skipped silently — these are pure decoders
# and have no log side effects.

def iter_vanish(data: bytes, cfg: PacketConfig) -> Iterator[EntityVanish]:
    """0x0080: [opcode:2][GID:4][reason:1]. 7 bytes total."""
    marker = struct.pack("<H", cfg.vanish)
    offset = 0
    while offset <= len(data) - 7:
        idx = data.find(marker, offset)
        if idx == -1 or idx + 7 > len(data):
            break
        gid = struct.unpack_from("<I", data, idx + 2)[0]
        vanish_type = data[idx + 6]
        if 100_000 <= gid <= 200_000_000:
            yield EntityVanish(gid=gid, vanish_type=vanish_type)
        offset = idx + 1


def iter_player_move(data: bytes, cfg: PacketConfig) -> Iterator[PlayerMovePos]:
    """0x0087: [opcode:2][tick:4][from→to:6]. 12 bytes total."""
    needle = struct.pack("<H", cfg.player_move)
    offset = 0
    while offset <= len(data) - 12:
        idx = data.find(needle, offset)
        if idx == -1 or idx + 12 > len(data):
            break
        fx, fy, tx, ty = decode_pos2(data, idx + 6)
        if 0 < fx <= 500 and 0 < fy <= 500 and 0 < tx <= 500 and 0 < ty <= 500:
            yield PlayerMovePos(from_x=fx, from_y=fy, to_x=tx, to_y=ty)
            return
        offset = idx + 1


def iter_map_change(data: bytes, cfg: PacketConfig) -> Iterator[MapChange]:
    """0x0091: [opcode:2][map_name:16 null-term][x:2][y:2]. 22 bytes total."""
    marker = struct.pack("<H", cfg.map_change)
    offset = 0
    while offset <= len(data) - 22:
        idx = data.find(marker, offset)
        if idx == -1 or idx + 22 > len(data):
            break
        map_name, x, y = _decode_map_change(data, idx)
        if map_name:
            yield MapChange(map_name=map_name, x=x, y=y)
            return
        offset = idx + 1


def _decode_map_change(data: bytes, idx: int) -> tuple[str, int, int]:
    map_bytes = data[idx + 2:idx + 18]
    null_pos = map_bytes.find(b"\x00")
    if null_pos >= 0:
        map_bytes = map_bytes[:null_pos]
    name = map_bytes.decode("utf-8", errors="replace")
    if name.endswith(".gat"):
        name = name[:-4]
    x = struct.unpack_from("<H", data, idx + 18)[0]
    y = struct.unpack_from("<H", data, idx + 20)[0]
    if (name and any(c.isalpha() for c in name)
            and 0 < x <= 500 and 0 < y <= 500):
        return name, x, y
    return "", 0, 0


def iter_status_change(data: bytes, cfg: PacketConfig) -> Iterator[StatusChange]:
    """0x00B0: [opcode:2][sp_type:2][value:4]. 8 bytes total."""
    marker = struct.pack("<H", cfg.status_change)
    offset = 0
    while offset <= len(data) - 8:
        idx = data.find(marker, offset)
        if idx == -1 or idx + 8 > len(data):
            break
        sp_type = struct.unpack_from("<h", data, idx + 2)[0]
        value = struct.unpack_from("<I", data, idx + 4)[0]
        if _probe("0x00B0"):
            logger.debug(
                "0x00B0 hit: sp_type=%d value=%d hex=%s",
                sp_type, value, _hex_window(data, idx),
            )
        yield StatusChange(type=sp_type, value=value)
        offset = idx + 8


def iter_status_change_long(
    data: bytes, cfg: PacketConfig,
) -> Iterator[StatusChange]:
    """0x0ACB ZC_PAR_CHANGE_LONG: [opcode:2][sp_type:2][value:8]. 12 bytes.

    Modern rAthena / client variant used when a stat value no longer fits
    in 32 bits (e.g. HP over ~2.1 bln). If the server uses this form, the
    legacy 0x00B0 cache stays empty — that's the symptom we're probing.
    """
    marker = struct.pack("<H", cfg.status_change_long)
    offset = 0
    while offset <= len(data) - 12:
        idx = data.find(marker, offset)
        if idx == -1 or idx + 12 > len(data):
            break
        sp_type = struct.unpack_from("<h", data, idx + 2)[0]
        value = struct.unpack_from("<q", data, idx + 4)[0]
        if _probe("0x0ACB"):
            logger.debug(
                "0x0ACB hit: sp_type=%d value=%d hex=%s",
                sp_type, value, _hex_window(data, idx),
            )
        yield StatusChange(type=sp_type, value=value)
        offset = idx + 12


def iter_stopmove(data: bytes, cfg: PacketConfig) -> Iterator[tuple[int, int, int]]:
    """0x0088 ZC_STOPMOVE: [opcode:2][GID:4][X:2][Y:2]. Yields (gid, x, y)."""
    marker = struct.pack("<H", cfg.stop_move)
    offset = 0
    while offset <= len(data) - 10:
        idx = data.find(marker, offset)
        if idx == -1 or idx + 10 > len(data):
            break
        gid = struct.unpack_from("<I", data, idx + 2)[0]
        x = struct.unpack_from("<H", data, idx + 6)[0]
        y = struct.unpack_from("<H", data, idx + 8)[0]
        if 0 < x <= 500 and 0 < y <= 500:
            yield gid, x, y
            offset = idx + 10
        else:
            offset = idx + 1
