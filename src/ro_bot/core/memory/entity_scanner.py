"""Entity struct lookup by GID.

Each mob / player in the engine is a struct whose first int32 is its
GID. Once we know one or more GIDs (from sniffer 0x0A30 packets), we
locate the structs on the heap and then read (X, Y) from
``+ENTITY_POS_OFFSET``.

Two public functions:

    find_entity_addrs_batch(process, gids)  # ~1 second heap scan, any N
    read_entity_pos(process, addr, gid)     # ~5 µs, cache-friendly

Critical detail: ``find_entity_addrs_batch`` walks the heap **once**
regardless of how many GIDs you pass in. This matters after a teleport
when the sniffer emits a burst of 0x0A30 packets — resolving them one
at a time would multiply latency by the burst size. See
:mod:`ro_bot.core.tracking.entity_tracker` for the cache that drains
the spawn queue greedily and feeds it through this function.
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


def find_entity_addrs_batch(
    process: ProcessHandle,
    gids: list[int],
    *,
    range_hint: tuple[int, int] | None = None,
) -> dict[int, int]:
    """Locate canonical struct addresses for every GID in `gids`.

    Single heap pass: covers any number of GIDs together. For each
    int32 hit we verify that ``+ENTITY_POS_OFFSET`` holds a plausible
    (X, Y); the first verifying address wins, later hits for the same
    GID are ignored.

    ``range_hint`` is forwarded to the underlying scan and limits the
    heap walk to a learned window. The caller (``EntityTracker``) keeps
    state and widens the hint as new addresses are observed.

    Returns ``{gid: addr}`` containing only the GIDs that were
    successfully located. Missing GIDs are left out (caller decides
    whether to retry with a wider window).
    """
    if not gids:
        return {}
    pending: set[int] = set(gids)
    found: dict[int, int] = {}
    for value, hit in process.scan_int32_aligned_multi(
        pending, range_hint=range_hint,
    ):
        if value in found:
            continue
        if read_entity_pos(process, hit, value) is not None:
            found[value] = hit
            if len(found) == len(pending):
                break
    return found
