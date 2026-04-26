# Architecture

Three layers with strict one-way dependencies:

```
app  →  hunt  →  core
```

| Layer | Responsibility | Forbidden imports |
|-------|----------------|-------------------|
| `core` | Low-level I/O + domain primitives (memory, HID, window, sniffer, projection, tracking). Server-agnostic. | `hunt`, `app` |
| `hunt` | Hunting business logic — controller + policies. No SQLite, no argparse. | `app` |
| `app` | SQLite schema + migrations + seed + profile / server models + wiring + CLI. | (top of stack) |

The `.cursor/rules/layering.mdc` rule enforces these boundaries
statically.

## Package layout

```
src/ro_bot/
├── __main__.py           # python -m ro_bot
├── cli.py                # argparse + entrypoint
├── core/
│   ├── logging_setup.py
│   ├── elevation.py
│   ├── hotkeys.py
│   ├── window.py
│   ├── hid/              # HidBridge protocol + ArduinoHidBridge
│   ├── memory/           # process + offsets + player_state + entity_scanner
│   ├── network/          # packets + parser + sniffer
│   ├── tracking/         # entity tracker (sniffer ∪ memory)
│   └── projection/       # CameraProjection
├── hunt/
│   ├── controller.py     # HuntController (orchestrator)
│   ├── loop.py           # run_hunt_loop
│   ├── config.py         # HuntConfig + policy sub-configs (frozen)
│   ├── constants.py      # non-profile tuning (poll rates, log cadences)
│   ├── event_bus.py      # sniffer-thread → tick-thread event queue
│   ├── pause.py          # PauseToken + shift helpers
│   ├── blacklist.py
│   ├── cell_observer.py  # per-GID cell-settle timer
│   ├── aim_service.py    # projection + HID + click
│   ├── dead_zones/       # DeadZone + filter
│   └── policies/         # targeting, engagement, heal, buffs, idle_action, escape
└── app/
    ├── db/               # connection + schema.sql + migrations + seed
    ├── models/           # Server, Profile (hydrated value classes)
    ├── repositories/     # SQL → model hydration
    ├── session.py        # BotSession: wires core + hunt from a Profile
    ├── runner.py         # run_hunt_for_profile(db_path, profile_name)
    └── ...
```

## Dataflow

```
CLI `ro-bot hunt --profile NAME`
  ↓
app.runner.run_hunt_for_profile
  ├─ open_db / apply_migrations / seed_defaults
  ├─ ProfileRepository.get_by_name → Profile (+ Server)
  └─ BotSession(profile).start()
       ├─ wait_for_game_window (poll up to 120s) + disable mouse accel
       ├─ ArduinoHidBridge.connect()
       ├─ PacketSniffer.connect()
       ├─ PlayerReader.connect() (OpenProcess + anchor scan)
       ├─ EntityTracker(process, sniffer).start()
       └─ HuntController(cfg, bridge, sniffer, tracker, player_reader, aim, zones)
  ↓
run_hunt_loop(controller, should_stop, toggle_pause)
  └─ tick(): heal → buffs → events → escape → engage / continue → target selection
```

## Why layers

- **Testability.** `core` can be unit-tested against mocks of the
  Win32 surface without touching SQLite or argparse; `hunt` can be
  tested against a fake `HidBridge` without real memory reads.
- **Server portability.** Memory offsets and packet IDs live in
  `core`; per-server overrides live in SQLite (`server_projection`,
  `server_dead_zone`). Adding a new private server is a row insert +
  an override — never a code change in `hunt`.
- **Size control.** Shallow layers with explicit interfaces let each
  file stay focused. Soft limit 300 lines, hard 500 — see
  `.cursor/rules/file-size.mdc`.

## Threads

Three threads run concurrently once the bot is up:

1. **Main thread** — ticks the `HuntController`. Reads memory,
   drives HID.
2. **Sniffer thread** — scapy `sniff()` loop. Only updates caches and
   fires callbacks (no blocking I/O).
3. **Entity-tracker scanner thread** — pops pending spawn GIDs from a
   queue and runs the ~1 s heap scan per GID.

State shared between them is the sniffer's entity dict, the event
bus, and the tracker's cache — each protected by a dedicated lock.
