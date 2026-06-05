"""Tests for post-patch entity name packet decoding."""

from __future__ import annotations

import struct

from ro_bot.core.network.entity_name_parser import (
    NAME_FIELD_LEN,
    REQNAMEALL_LONG_SIZE,
    REQNAMEALL_NPC_SIZE,
    REQNAME_SHORT_SIZE,
    normalize_entity_name,
    scan_entity_name_packets,
)
from ro_bot.core.network.packets import PacketConfig


def _pack_name(name: str) -> bytes:
    raw = name.encode("utf-8")[:NAME_FIELD_LEN]
    return raw + b"\x00" * (NAME_FIELD_LEN - len(raw))


def test_reqnameall_long_stride_does_not_corrupt_name() -> None:
    """106 B 0x0A30 must not re-scan party/guild fields as a second entity."""
    gid = 123_456_789
    mob = "Peco Peco"
    buf = bytearray(REQNAMEALL_LONG_SIZE + 4)
    struct.pack_into("<HI", buf, 0, 0x0A30, gid)
    buf[6:6 + NAME_FIELD_LEN] = _pack_name(mob)
    # party/guild/position left empty; title_id = 0 at end
    hits = scan_entity_name_packets(bytes(buf), PacketConfig())
    names = [e.name for e in hits if e.gid == gid]
    assert names == [mob]


def test_reqnameall_npc_mob_name() -> None:
    gid = 150_000_001
    mob = "Muka"
    buf = bytearray(REQNAMEALL_NPC_SIZE)
    struct.pack_into("<HII", buf, 0, 0x0ADF, gid, 1002)
    buf[10:10 + NAME_FIELD_LEN] = _pack_name(mob)
    hits = scan_entity_name_packets(bytes(buf), PacketConfig())
    assert any(e.gid == gid and e.name == mob for e in hits)


def test_legacy_short_0x95_with_hp_text() -> None:
    gid = 150_000_002
    mob = "Sohee"
    tail = b"HP: 1200/1200\x00"
    buf = (
        struct.pack("<HI", 0x0095, gid)
        + _pack_name(mob)
        + tail
    )
    hits = scan_entity_name_packets(buf, PacketConfig())
    match = [e for e in hits if e.gid == gid]
    assert len(match) == 1
    assert match[0].name == mob
    assert match[0].hp == 1200
    assert match[0].max_hp == 1200


def test_monster_hp_binary() -> None:
    gid = 150_000_003
    buf = struct.pack("<HIii", 0x0977, gid, 500, 1000)
    hits = scan_entity_name_packets(buf, PacketConfig())
    assert len(hits) == 1
    assert hits[0].gid == gid
    assert hits[0].name == ""
    assert hits[0].hp == 500
    assert hits[0].max_hp == 1000


def test_normalize_skips_hp_percent_title() -> None:
    raw = "85%\x00Mantis"
    assert normalize_entity_name(raw) == "Mantis"
