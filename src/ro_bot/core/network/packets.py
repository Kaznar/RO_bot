"""Ragnarok Online packet dataclasses and IDs (plaintext subset).

Gepard Shield encrypts entity spawn / move packets (0x09FF, 0x09FD,
0x0086). We bypass that by reading the plaintext packets the server
still emits:

    0x0A30 — ZC_ACK_REQNAMEALL (name + party/guild/…, long form)
    0x0ADF — ZC_ACK_REQNAMEALL_NPC (mob/NPC name + title)
    0x0095 — ZC_ACK_REQNAME (legacy short name)
    0x0977 — ZC monster HP (binary HP / maxHP)
    0x0080 — entity vanish (7 bytes)
    0x0087 — player movement (12 bytes)
    0x0091 — map change (22 bytes)
    0x00B0 — status change / HP sync (8 bytes, 32-bit value)
    0x0ACB — status change LONG (modern rAthena, 12 bytes, 64-bit value)
    0x0088 — entity stop-move / position (10 bytes)

This module keeps only data shapes; parsing lives in
:mod:`ro_bot.core.network.parser`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class VanishType(IntEnum):
    OUT_OF_SIGHT = 0
    DIED = 1
    LOGGED_OUT = 2
    TELEPORT = 3


@dataclass(frozen=True)
class PacketConfig:
    """Packet IDs. Defaults match NexusRO; keep in sync with the
    prototype's experimentally-verified values.
    """
    entity_name_hp: int = 0x0A30
    entity_name_npc: int = 0x0ADF
    entity_name_short: int = 0x0095
    entity_monster_hp: int = 0x0977
    vanish: int = 0x0080
    player_move: int = 0x0087
    map_change: int = 0x0091
    status_change: int = 0x00B0
    status_change_long: int = 0x0ACB
    stop_move: int = 0x0088


@dataclass(frozen=True)
class EntityNameHp:
    gid: int
    name: str
    hp: int
    max_hp: int


@dataclass(frozen=True)
class EntityVanish:
    gid: int
    vanish_type: int


@dataclass(frozen=True)
class PlayerMovePos:
    from_x: int
    from_y: int
    to_x: int
    to_y: int


@dataclass(frozen=True)
class MapChange:
    map_name: str
    x: int
    y: int


@dataclass(frozen=True)
class StatusChange:
    type: int
    value: int


# SP/Stat sub-type IDs used inside 0x00B0 ZC_PAR_CHANGE. HP is our
# canonical source of player HP — the memory slot is unreliable.
SP_HP = 5
SP_MAXHP = 6
