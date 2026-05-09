#!/usr/bin/env python3
"""Scan process memory near the character-name anchor for weight (cur/max).

Run **as Administrator** with the client logged in on the target character.
Pass the exact **current** and **max weight** shown in-game (status window).

Example::

    uv run python scripts/find_weight_in_memory.py --char JoJo --current 908 --max 5690

If nothing matches, widen ``--below`` / ``--above`` (bytes searched below /
above the anchor). The client may store weight as **int16** pairs, **reversed**
order, or with **padding** between the two int32s — this script tries those
layouts automatically.

After you get a stable pair of offsets, add them to ``MemoryOffsets`` +
``PlayerReader.read()`` and document in ``docs/memory-offsets.md``.

This repo does not ship Cheat Engine; this script reuses the same anchor
logic as :class:`ro_bot.core.memory.player_state.PlayerReader`.
"""

from __future__ import annotations

import argparse
import logging
import struct
import sys
from dataclasses import dataclass

from ro_bot.core.memory.offsets import MemoryOffsets
from ro_bot.core.memory.player_state import PlayerReader

logger = logging.getLogger("find_weight")


@dataclass(frozen=True)
class _Hit:
    rel_cur: int
    rel_max: int
    layout: str


def _read_u16(proc, addr: int) -> int | None:
    b = proc.read_bytes(addr, 2)
    if b is None or len(b) < 2:
        return None
    return struct.unpack("<H", b)[0]


def _read_i16(proc, addr: int) -> int | None:
    b = proc.read_bytes(addr, 2)
    if b is None or len(b) < 2:
        return None
    return struct.unpack("<h", b)[0]


def _collect_hits(
    proc,
    anchor: int,
    cur: int,
    mx: int,
    below: int,
    above: int,
    gaps: tuple[int, ...],
) -> list[_Hit]:
    hits: list[_Hit] = []
    seen: set[tuple[int, int, str]] = set()

    def add(rel_cur: int, rel_max: int, layout: str) -> None:
        """rel_* = byte offset from anchor to that field's int32."""
        key = (rel_cur, rel_max, layout)
        if key in seen:
            return
        seen.add(key)
        hits.append(_Hit(rel_cur=rel_cur, rel_max=rel_max, layout=layout))

    rel = -below
    while rel <= above:
        addr = anchor + rel
        # int32 cur, int32 max with optional extra dword between / after first
        for gap in gaps:
            a = proc.read_int32(addr)
            b = proc.read_int32(addr + 4 + gap)
            if a is None or b is None:
                continue
            if a == cur and b == mx:
                add(rel, rel + 4 + gap, f"int32 cur @+0, int32 max @+{4 + gap} (gap={gap})")
            if a == mx and b == cur:
                # max dword first in memory, current at +4+gap
                add(
                    rel + 4 + gap,
                    rel,
                    f"int32 max @+0, int32 cur @+{4 + gap} (gap={gap})",
                )

        rel += 4

    # int16 / uint16 pairs (2-byte aligned)
    rel = -below
    while rel <= above:
        addr = anchor + rel
        u0, u1 = _read_u16(proc, addr), _read_u16(proc, addr + 2)
        if u0 is not None and u1 is not None:
            if u0 == cur and u1 == mx:
                add(rel, rel + 2, "uint16 cur @+0, uint16 max @+2")
            if u0 == mx and u1 == cur:
                add(rel, rel + 2, "uint16 max @+0, uint16 cur @+2")
        s0, s1 = _read_i16(proc, addr), _read_i16(proc, addr + 2)
        if s0 is not None and s1 is not None:
            if s0 == cur and s1 == mx:
                add(rel, rel + 2, "int16 cur @+0, int16 max @+2")
            if s0 == mx and s1 == cur:
                add(rel, rel + 2, "int16 max @+0, int16 cur @+2")
        rel += 2

    hits.sort(key=lambda h: (abs(h.rel_cur), h.layout))
    return hits


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--process", default="nexusro.exe",
        help="Client executable name (substring match).",
    )
    p.add_argument("--char", required=True, help="Character name (anchor string).")
    p.add_argument("--current", type=int, required=True, help="Current weight from UI.")
    p.add_argument("--max", type=int, required=True, help="Max weight from UI.")
    p.add_argument(
        "--below", type=lambda x: int(x, 0), default=0x200_000,
        help="Bytes to scan below anchor (hex or decimal), default 0x200000.",
    )
    p.add_argument(
        "--above", type=lambda x: int(x, 0), default=0x20_000,
        help="Bytes to scan above anchor (hex or decimal), default 0x20000.",
    )
    p.add_argument(
        "--gaps",
        type=lambda s: tuple(int(x.strip(), 0) for x in s.split(",") if x.strip()),
        default="0,4,8,12,16,20,24,28,32",
        help="Extra bytes between first and second int32 (comma-separated).",
    )
    p.add_argument(
        "--wait", type=float, default=120.0,
        help="Seconds to wait for process + anchor.",
    )
    args = p.parse_args()

    if args.current < 0 or args.max <= 0 or args.current > args.max:
        print("error: expect 0 <= current <= max and max > 0", file=sys.stderr)
        return 2

    reader = PlayerReader(args.process, args.char)
    if not reader.connect(wait_timeout=args.wait):
        return 1
    try:
        anchor = reader.anchor_address
        proc = reader.process
        cur, mx = args.current, args.max
        o = MemoryOffsets()

        st = reader.read()
        print(f"anchor = 0x{anchor:08X}")
        print(
            f"player snapshot (memory): pos=({st.x},{st.y}) "
            f"HP={st.hp}/{st.hp_max} SP={st.sp}/{st.sp_max}",
        )
        chk = proc.read_int32(anchor + o.hp_max)
        print(
            f"sanity: anchor+hp_max_off (0x{o.hp_max:X}) → int32 {chk} "
            f"(expect ~{st.hp_max} if slot matches docs)",
        )

        print(f"looking for weight cur={cur} max={mx} (patterns + gaps) …")
        hits = _collect_hits(
            proc, anchor, cur, mx, args.below, args.above, args.gaps,
        )

        if not hits:
            print(
                "no matches in range. Try:\n"
                "  • larger --below / --above\n"
                "  • more --gaps (e.g. add 36,40,...)\n"
                "  • confirm numbers match the client status window exactly",
            )
            return 3

        print(f"found {len(hits)} candidate(s):\n")
        for h in hits:
            print(f"  {h.layout}")
            print(
                f"    anchor + 0x{h.rel_cur:X}  (= {h.rel_cur:+d}) → current\n"
                f"    anchor + 0x{h.rel_max:X}  (= {h.rel_max:+d}) → max\n",
            )
        if len(hits) > 1:
            print(
                "multiple hits: change weight in-game, re-run with new "
                "--current/--max, and keep the offset pair that still matches.",
            )
    finally:
        reader.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
