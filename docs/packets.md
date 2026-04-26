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
| `0x0A30` | S→C | entity name + HP | variable | Mob names, HP%, whitelist match |
| `0x0080` | S→C | entity vanish | 7 B | Death / out-of-sight → blacklist |
| `0x0087` | S→C | player move | 12 B | Player path (not used for HP) |
| `0x0088` | S→C | entity stop-move | 10 B | **Only plaintext mob position** |
| `0x0091` | S→C | map change | 22 B | Map reset, cache wipe |
| `0x00B0` | S→C | status change | 8 B | Player HP / MAXHP |

Gepard Shield encrypts `0x09FF` / `0x09FD` / `0x0086` (entity
spawn / move). Memory scan handles those positions instead.

## Layouts

### `0x0A30` — entity name + HP

Variable length. `PacketParser` scans the TCP payload byte-by-byte
looking for:

```
[2B] opcode  (BE 0x0A30)
[4B] GID
... name (null-padded, ~24 B typical, up to 96 B) ...
[4B] HP current
[4B] HP max
```

Because the name field is variable, the parser tries candidate
lengths and validates with `hp ≤ hp_max` + printable ASCII. Tuned
for NexusRO but works on any eAthena fork that uses the same opcode.

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
