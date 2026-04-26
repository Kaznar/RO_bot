"""Entity struct lookup by GID.

Each mob / player in the engine is a struct whose first int32 is its
GID. Once we know a GID (from a sniffer 0x0A30 packet), we locate the
struct on the heap and then read (X, Y) from `+ENTITY_POS_OFFSET`.

Two public functions:

    find_entity_addr(process, gid)   # ~1 second heap scan
    read_entity_pos(process, addr, gid)  # ~5 µs, cache-friendly

The design is such that you scan once per spawn and then poll the
resulting address cheaply. See :mod:`ro_bot.core.tracking.entity_tracker`
for the cache that ties the two together.
"""

from __future__ import annotations

import struct

from ro_bot.core.memory.offsets import (
    ENTITY_GID_OFFSET,
    ENTITY_POS_OFFSET,
    ENTITY_POS_SIZE,
    MAP_COORD_MAX,
    MAP_COORD_MIN,
)
from ro_bot.core.memory.process import ProcessHandle


def read_entity_pos(
    process: ProcessHandle, gid_addr: int, expected_gid: int,
) -> tuple[int, int] | None:
    """Read (X, Y) at `gid_addr`, defending against slot recycle / torn writes.

    Returns None if:
      - the read fails,
      - the int32 at `+0` no longer equals `expected_gid` (engine
        reused the slot for another entity),
      - or the resulting (X, Y) falls outside the map coord range
        (torn write during map change, or garbage).

    Cost: one 100-byte ReadProcessMemory (~5 µs).
    """
    data = process.read_bytes(
        gid_addr, ENTITY_GID_OFFSET + ENTITY_POS_OFFSET + ENTITY_POS_SIZE,
    )
    if data is None or len(data) < ENTITY_POS_OFFSET + ENTITY_POS_SIZE:
        return None
    stored_gid = struct.unpack_from("<I", data, ENTITY_GID_OFFSET)[0]
    if stored_gid != (expected_gid & 0xFFFFFFFF):
        return None
    x = struct.unpack_from("<i", data, ENTITY_POS_OFFSET)[0]
    y = struct.unpack_from("<i", data, ENTITY_POS_OFFSET + 4)[0]
    if not (MAP_COORD_MIN <= x <= MAP_COORD_MAX
            and MAP_COORD_MIN <= y <= MAP_COORD_MAX):
        return None
    return x, y


def find_entity_addr(process: ProcessHandle, gid: int) -> int | None:
    """Locate the canonical struct address for `gid`, or None.

    Algorithm: scan the heap for `int32(gid)`, then for each hit verify
    that `+ENTITY_POS_OFFSET` holds a plausible (X, Y). Takes ~1 second
    in practice — callers should cache the result and only re-scan when
    `read_entity_pos` returns None (slot recycled).
    """
    for hit in process.scan_int32_aligned(gid):
        if read_entity_pos(process, hit, gid) is not None:
            return hit
    return None
