"""Constants and offsets for NexusRO process memory.

Offsets are server/client-specific; these match the NexusRO client used
by the prototype. If a new private server ships a different build, the
values here may need adjusting — hence being kept in one place.

Sources:
    - Player stats offsets: empirical, anchored to the character-name
      string in memory. See docs/memory-offsets.md.
    - Entity struct layout: `+0 GID int32`, `+92/+96 X/Y int32`. See
      docs/memory-offsets.md.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Win32 / WinAPI ───────────────────────────────────────────────────
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100
SNAPPROCESS = 0x00000002

# ── Entity struct ────────────────────────────────────────────────────
ENTITY_GID_OFFSET = 0
ENTITY_POS_OFFSET = 92
ENTITY_POS_SIZE = 8  # two int32s at +92 (X) and +96 (Y)

# Sane RO map coordinate range. Reads outside this range are treated
# as torn writes or garbage (see `read_entity_pos`).
MAP_COORD_MIN = 1
MAP_COORD_MAX = 500

# Skip the low ~1 MB region (PE image / static data / NT loader).
# Entities live on the user heap — typically above 0x00100000 on x86.
ENTITY_SCAN_MIN_ADDR = 0x00100000
ENTITY_SCAN_MAX_ADDR = 0x7FFFFFFF


@dataclass(frozen=True)
class MemoryOffsets:
    """Offsets relative to the character-name anchor address.

    Negative values because the anchor is the player's name string and
    the player stat fields live earlier in the same struct.
    """
    player_x: int = -0x1A3D4
    player_y: int = -0x1A3D0
    hp_current: int = -0x2C50
    hp_max: int = -0x2C4C
    sp_current: int = -0x2C48
    sp_max: int = -0x2C44
