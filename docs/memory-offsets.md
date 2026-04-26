# Memory offsets

All live memory access goes through `core/memory/`:

- `process.py` — low-level `ProcessHandle` (OpenProcess, RPM,
  VirtualQueryEx, byte-pattern scan).
- `offsets.py` — the constants documented below.
- `player_state.py` — `PlayerReader`: connects to the game process,
  anchors on the character-name string, returns `(x, y, hp, sp)`.
- `entity_scanner.py` — heap scan to resolve a GID to its entity
  struct address + position read.

Requires admin. Without `PROCESS_VM_READ` every read returns 0.

## Player state — character-name anchor

We scan the game process memory for the literal bytes
`\x00<char_name>\x00` once at session start. That address is the
**anchor**; everything below is relative to it.

| Symbol | Offset (hex) | Type | What it is |
|--------|--------------|------|------------|
| `player_x` | `-0x1A3D4` | int32 | Cell X coordinate |
| `player_y` | `-0x1A3D0` | int32 | Cell Y coordinate |
| `hp_current` | `-0x2C50` | int32 | **Do not use.** See below. |
| `hp_max` | `-0x2C4C` | int32 | Player max HP |
| `sp_current` | `-0x2C48` | int32 | Player SP |
| `sp_max` | `-0x2C44` | int32 | Player max SP |

### Why HP comes from the sniffer, not memory

The `hp_current` slot is shared between **player HP** and
**currently-targeted entity HP** — the game UI binds both progress
bars to the same int32. Reading it for heal decisions would
randomly trigger potion spam whenever a low-HP mob was selected.

**Actual source of truth:** `PacketSniffer.get_player_hp() →
(current, max)` driven by 0x00B0 `ZC_PAR_CHANGE`:

- `sp_type=5` → `SP_HP`
- `sp_type=6` → `SP_MAXHP`

Latency ~50–150 ms (one network roundtrip) — well within tick
cadence.

### Offsets may drift

Game client updates can shift every offset here. If an update
breaks the bot:

1. Verify anchor still finds the character name (check logs).
2. Re-derive offsets with an external tool (Cheat Engine pointer
   scan or the `tools/test_memory.py` REPL in the legacy repo).
3. Update the defaults in `core/memory/offsets.py`.

Per-server overrides would belong in a future `server_memory_offsets`
table — not needed yet.

## Entity struct — GID + position

Heap-allocated entity structs have a fixed header:

```
+0    int32   GID            ← we search for this
+92   int32   cell X
+96   int32   cell Y
```

`entity_scanner.find_entity_addr(process, gid)`:

1. Iterates committed, readable, non-guard pages via
   `VirtualQueryEx`.
2. In each page scans for the 4 bytes of GID.
3. Validates the hit by reading X,Y at `+92/+96` and checking they
   are within `MAP_COORD_MIN..MAP_COORD_MAX` (1..500).
4. Caches the address; next read is a single RPM.

`read_entity_pos(process, addr, expected_gid)` revalidates the GID
on every call so we reject stale slots after the heap recycles.

### Scan range

```
ENTITY_SCAN_MIN_ADDR = 0x00100000
ENTITY_SCAN_MAX_ADDR = 0x7FFFFFFF
```

Skips the low 1 MB (PE / NT loader) — entities live on the user
heap, typically above 1 MB.

## Research notes

More exploratory findings (display structs at `0x0476xxxx`, mob
definition tables, sprite name table, false-positive signatures,
`findgid` approach) are preserved here:

- Entity struct layout, failed HP approaches, false positives, and
  alternative approaches (`findgid`, disassembly) were all
  investigated during the prototype; see the
  [legacy research dump](#legacy-research-dump) below.

## Legacy research dump

Kept verbatim from the prototype so we don't lose context.

### Entities under Gepard Shield

Gepard Shield encrypts `0x09FF` / `0x09FD` / `0x0086`. Only
`0x0088 ZC_STOPMOVE` passes in plaintext → the only sniffer-level
source of mob positions. Everything else comes from the memory
scan.

### Display struct vs. game-object struct

`\x00<name>\x00` hits also surface a **display struct** at
`0x0476xxxx–0x0479xxxx`:

```
name - 84 ... name - 82   int16 pair (tracks player pos — render origin, NOT mob pos)
name - 80                 000000C8 constant (sprite height?)
name - 68                 00F60300 constant
name - 52                 xxD200xx pointer
name - 20                 xxD58800 / xxE88800 pointer
name - 16                 00100000 (4096)
name - 12..-4             00FFFFFF FFFFFFFF FF000000 → alive; 00FE0100 00D70000 00000000 → dead/faded
name + 0                  entity name (padded)
```

Do not confuse with the entity game-object at `+0 GID / +92 X / +96
Y` — that's the one the bot uses.

### HP memory dead end (resolved)

- `-0x2C50` bimodal (player + target).
- Multi-anchor probe: always a single valid anchor.
- ±24 B and ±256 B windows: nothing else moves.
- Sniffer 0x00B0 chosen instead. Permanent.
