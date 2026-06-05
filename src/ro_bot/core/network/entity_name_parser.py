"""Decoders for entity name / HP packets (0x0A30, 0x0ADF, 0x0095, 0x0977).

NexusRO and modern rAthena forks expanded ``ZC_ACK_REQNAMEALL`` (0x0A30)
from a ~30 B name-only blob to ~106 B (name + party + guild + position +
title_id). Scanning with a fixed 30 B stride re-parses party/guild fields as
fake GIDs and wipes mob names — common after client patches that show element
+ HP%% on the overhead bar.
"""

from __future__ import annotations

import logging
import re
import struct

from ro_bot.core.network.packets import EntityNameHp, PacketConfig

logger = logging.getLogger(__name__)

NAME_FIELD_LEN = 24
# ZC_ACK_REQNAMEALL (PACKETVER >= 20150225): op + gid + 4×name[24] + title_id
REQNAMEALL_LONG_SIZE = 2 + 4 + NAME_FIELD_LEN * 4 + 4
# ZC_ACK_REQNAME (0x95): op + gid + name[24]
REQNAME_SHORT_SIZE = 2 + 4 + NAME_FIELD_LEN
# ZC_ACK_REQNAMEALL_NPC (0x0ADF, modern): op + gid + groupId + name + title
REQNAMEALL_NPC_SIZE = 2 + 4 + 4 + NAME_FIELD_LEN * 2
MONSTER_HP_SIZE = 2 + 4 + 4 + 4

_HP_PATTERN = re.compile(rb"HP:\s*(\d+)/(\d+)")
_HP_PATTERN_LOOSE = re.compile(rb"HP\s*:?\s*(\d+)\s*/\s*(\d+)")
_HP_PERCENT = re.compile(rb"(\d+)\s*%")
_GARBAGE_NAME = re.compile(
    r"^(?:HP\s*:?\s*\d|(?:\d+\s*%))", re.IGNORECASE,
)


def _read_cstring(data: bytes, offset: int, max_len: int = NAME_FIELD_LEN) -> str:
    end = min(offset + max_len, len(data))
    chunk = data[offset:end]
    null_pos = chunk.find(b"\x00")
    if null_pos >= 0:
        chunk = chunk[:null_pos]
    return chunk.decode("utf-8", errors="replace").strip()


def normalize_entity_name(raw: str) -> str:
    """Pick the display mob name from a fixed 24 B field or garbled tail."""
    if not raw:
        return ""
    candidates: list[str] = []
    for part in raw.split("\x00"):
        part = part.strip()
        if part and not _GARBAGE_NAME.match(part):
            candidates.append(part)
    if not candidates:
        printable = "".join(
            c for c in raw if c.isprintable() and ord(c) < 0x10000
        ).strip()
        match = re.search(
            r"([A-Za-z][A-Za-z0-9][A-Za-z0-9 \-']{0,22})",
            printable,
        )
        return match.group(1).strip() if match else ""
    return max(candidates, key=len)


def looks_like_entity_name(name: str) -> bool:
    if not (1 <= len(name) <= NAME_FIELD_LEN):
        return False
    if not any(c.isalpha() for c in name):
        return False
    printable = sum(
        1 for c in name if c.isprintable() and ord(c) < 0x10000
    )
    return printable >= len(name) * 0.6


def _plausible_gid(gid: int) -> bool:
    return (
        100_000 <= gid <= 200_000_000
        or 3_000_000 <= gid <= 4_000_000
    )


def _extract_hp_text(data: bytes, start_idx: int) -> tuple[int, int]:
    search_end = min(start_idx + 160, len(data))
    window = data[start_idx:search_end]
    m = _HP_PATTERN.search(window)
    if m is None:
        m = _HP_PATTERN_LOOSE.search(window)
    if m is not None:
        return int(m.group(1)), int(m.group(2))
    m_pct = _HP_PERCENT.search(window)
    if m_pct is not None:
        pct = int(m_pct.group(1))
        return pct, 100
    return 0, 0


def _reqnameall_advance(data: bytes, idx: int) -> int:
    if idx + REQNAMEALL_LONG_SIZE <= len(data):
        return REQNAMEALL_LONG_SIZE
    search_end = min(idx + 160, len(data))
    for pattern in (_HP_PATTERN, _HP_PATTERN_LOOSE):
        m = pattern.search(data, idx + REQNAME_SHORT_SIZE, search_end)
        if m is not None:
            return max(REQNAME_SHORT_SIZE, m.end() - idx + 2)
    return REQNAME_SHORT_SIZE


def _scan_marker_name_packet(
    data: bytes,
    opcode: int,
    *,
    name_offset: int,
    packet_size: int,
    hp_from_text: bool = False,
) -> list[EntityNameHp]:
    results: list[EntityNameHp] = []
    marker = struct.pack("<H", opcode)
    search_start = 0
    min_tail = name_offset + NAME_FIELD_LEN
    while True:
        idx = data.find(marker, search_start)
        if idx == -1 or idx + min_tail > len(data):
            break
        gid = struct.unpack_from("<I", data, idx + 2)[0]
        raw = _read_cstring(data, idx + name_offset)
        name = normalize_entity_name(raw)
        if not _plausible_gid(gid) or not looks_like_entity_name(name):
            search_start = idx + 2
            continue
        if hp_from_text:
            hp, max_hp = _extract_hp_text(data, idx)
            advance = (
                _reqnameall_advance(data, idx)
                if packet_size == REQNAMEALL_LONG_SIZE
                else packet_size
            )
        else:
            hp, max_hp = 0, 0
            advance = packet_size
        results.append(EntityNameHp(
            gid=gid, name=name, hp=hp, max_hp=max_hp,
        ))
        search_start = idx + advance
    return results


def _scan_monster_hp(data: bytes, opcode: int) -> list[EntityNameHp]:
    results: list[EntityNameHp] = []
    marker = struct.pack("<H", opcode)
    search_start = 0
    while True:
        idx = data.find(marker, search_start)
        if idx == -1 or idx + MONSTER_HP_SIZE > len(data):
            break
        gid = struct.unpack_from("<I", data, idx + 2)[0]
        hp = struct.unpack_from("<i", data, idx + 6)[0]
        max_hp = struct.unpack_from("<i", data, idx + 10)[0]
        if (
            not _plausible_gid(gid)
            or max_hp <= 0
            or hp < 0
            or hp > max_hp
        ):
            search_start = idx + 2
            continue
        results.append(EntityNameHp(
            gid=gid, name="", hp=hp, max_hp=max_hp,
        ))
        search_start = idx + MONSTER_HP_SIZE
    return results


def scan_entity_name_packets(
    data: bytes,
    cfg: PacketConfig,
) -> list[EntityNameHp]:
    """Scan a TCP payload for every supported name/HP opcode."""
    out: list[EntityNameHp] = []
    out.extend(_scan_marker_name_packet(
        data,
        cfg.entity_name_hp,
        name_offset=6,
        packet_size=REQNAMEALL_LONG_SIZE,
        hp_from_text=True,
    ))
    out.extend(_scan_marker_name_packet(
        data,
        cfg.entity_name_npc,
        name_offset=10,
        packet_size=REQNAMEALL_NPC_SIZE,
    ))
    out.extend(_scan_marker_name_packet(
        data,
        cfg.entity_name_short,
        name_offset=6,
        packet_size=REQNAME_SHORT_SIZE,
        hp_from_text=True,
    ))
    out.extend(_scan_monster_hp(data, cfg.entity_monster_hp))
    return out
