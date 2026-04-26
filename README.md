# RO_bot

Ragnarok Online hunting bot. Watches the game client via TCP packet
sniffing + process memory, aims and clicks mobs through an Arduino HID
bridge, refreshes buffs and heals itself. One CLI mode: `hunt`.

## Quick start

1. Install Python 3.12+ and [`uv`](https://docs.astral.sh/uv/).
2. Install [Npcap](https://nmap.org/npcap/) (WinPcap API compatibility mode).
3. Clone, then `uv sync` in the repo root.
4. Flash the Arduino Pro Micro with the HID firmware from
   `docs/setup.md`.
5. First run will auto-create `profiles.db` with a `default` profile.
   Edit it in [DB Browser for SQLite](https://sqlitebrowser.org/) to
   point at your character, mobs, maps and HUD.
6. Launch the game, log in to your character, then:

```
uv run ro-bot hunt --profile default
```

Hotkeys (global): `0` = quit, `p` = pause / resume.

## Documentation index

| File | What it covers |
|------|----------------|
| [`docs/architecture.md`](docs/architecture.md) | Layers, dataflow, import direction |
| [`docs/hunt-state-machine.md`](docs/hunt-state-machine.md) | Tick order, engagement FSM, policies |
| [`docs/config-profiles.md`](docs/config-profiles.md) | SQLite schema, how to add / edit profiles |
| [`docs/memory-offsets.md`](docs/memory-offsets.md) | Player / entity memory offsets, research notes |
| [`docs/packets.md`](docs/packets.md) | RO packet formats the sniffer parses |
| [`docs/setup.md`](docs/setup.md) | Arduino firmware, Npcap, admin, first run |

## Requirements

- Windows 10/11 (Win32 APIs, ShellExecute elevation, scapy+Npcap).
- Admin: memory reads need `PROCESS_VM_READ`; the bot auto-relaunches
  itself elevated unless you pass `--no-elevate`.
- One Arduino Pro Micro (or compatible) running the HID firmware — no
  ``SendInput``/``mouse_event`` synthetic input is used.
