# Packets

The sniffer lives in `core/network/`:

- `packets.py` — dataclasses + `PacketConfig` (opcode IDs).
- `parser.py` — pure decoders (`PacketParser` + `iter_*`).
- `sniffer.py` — scapy `sniff()` thread + caches + listener API.

All parsing is big-endian unless noted. `scapy` hands us raw TCP
payloads; we don't care about headers or fragmentation (RO opcodes
are small, typically one per segment).

## Opcodes we decode

| ID | Direction | Name | Size | Source of… |
|----|-----------|------|------|------------|
| `0x0A30` | S→C | ZC_ACK_REQNAMEALL | ~106 B | Primary mob/player name (long form) |
| `0x0ADF` | S→C | ZC_ACK_REQNAMEALL_NPC | ~58 B | Mob/NPC name + title (post-2017 clients) |
| `0x0095` | S→C | ZC_ACK_REQNAME | 30 B+ | Legacy short name (+ optional ``HP:`` text) |
| `0x0977` | S→C | monster HP | 14 B | Binary HP / maxHP (name may arrive separately) |
| `0x0080` | S→C | entity vanish | 7 B | Death / out-of-sight → blacklist |
| `0x0087` | S→C | player move | 12 B | Player path (not used for HP) |
| `0x0088` | S→C | entity stop-move | 10 B | **Only plaintext mob position** |
| `0x0091` | S→C | map change | 22 B | Map reset, cache wipe |
| `0x00B0` | S→C | status change | 8 B | Player HP / MAXHP |

Gepard Shield encrypts `0x09FF` / `0x09FD` / `0x0086` (entity
spawn / move). Memory scan handles those positions instead.

## Layouts

### Entity name / HP opcodes

Decoded in `core/network/entity_name_parser.py` (called from
`PacketParser.scan_for_entities`).

**`0x0A30` — ZC_ACK_REQNAMEALL** (modern, ~106 B):

```
[2B] opcode
[4B] GID
[24B] name
[24B] party
[24B] guild
[24B] position
[4B] title_id
```

The bot must advance by the full packet size. A legacy 30 B stride
re-parses party/guild bytes as fake GIDs and clears mob names.

**`0x0ADF` — ZC_ACK_REQNAMEALL_NPC** (~58 B): `GID`, `groupId`,
`name[24]`, `title[24]` (title may hold ``HP:`` / ``%`` UI text).

**`0x0095` — ZC_ACK_REQNAME**: `GID` + `name[24]`; some shards append
``HP: cur/max`` as ASCII.

**`0x0977` — monster HP**: `GID` + `int32 HP` + `int32 maxHP` (updates
cache only; spawn still needs a name packet).

### `0x0080` — `ZC_NOTIFY_VANISH`

```
[2B] opcode
[4B] GID
[1B] reason   0 OUT_OF_SIGHT, 1 DIED, 2 LOGGED_OUT, 3 TELEPORT
```

### `0x0087` — `ZC_NOTIFY_PLAYERMOVE`

```
[2B] opcode
[4B] tick
[6B] packed from+to position (pos2)
```

Positions are packed 4-nibble cells (the legacy RO
`WBUFPOS2` / `RBUFPOS2` format) → `decode_pos2` in `parser.py`.

### `0x0088` — `ZC_STOPMOVE`

```
[2B] opcode
[4B] GID
[2B] X
[2B] Y
```

Plaintext — our only positional ground truth for mobs when Gepard
is active.

### `0x0091` — `ZC_NPCACK_MAPMOVE`

```
[2B] opcode
[16B] map filename (null-padded, e.g. "prt_fild08.gat")
[2B] X
[2B] Y
```

Triggers a cache wipe in `PacketSniffer`, `EntityTracker`, and
`EngagementMachine`. Heal / buff / idle timers persist.

### `0x00B0` — `ZC_PAR_CHANGE`

```
[2B] opcode
[2B] sp_type
[4B] value
```

Relevant `sp_type`s:

| Value | Meaning |
|-------|---------|
| `5`   | `SP_HP` — current HP |
| `6`   | `SP_MAXHP` — max HP |

Everything else is ignored (STR/INT/Zeny/etc.).

## Sniffer API surface

- `PacketSniffer.start()` / `.stop()` — thread lifecycle.
- `.entities()` → `dict[gid, EntityNameHp]` snapshot (locked copy).
- `.get_player_hp()` → `(cur, max)`.
- `.current_map()` → str.
- Event listeners:
  - `on_vanish(cb)` → `(gid, vanish_type)` on 0x0080
  - `on_map_change(cb)` → `(map_name,)` on 0x0091
  - `on_stop_move(cb)` → `(gid, x, y)` on 0x0088

Hunt layer consumes these via `hunt.event_bus.EventBus`, which
converts sniffer-thread callbacks into tick-thread events.

## Adding a new opcode

1. Add the ID + shape dataclass to `packets.py`.
2. Add `iter_<name>(data, cfg)` in `parser.py` (pure, no state).
3. Handle it in `PacketSniffer._on_packet` — update cache, fire
   listeners.
4. Expose a typed getter on the sniffer if the hunt layer needs
   read access.

Never import scapy from the hunt layer.
