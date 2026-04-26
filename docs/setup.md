# Setup

## Prerequisites

- **Windows 10 / 11.** Win32-only (ShellExecute elevation, scapy over
  Npcap, ctypes RPM).
- **Python 3.12+** managed with [`uv`](https://docs.astral.sh/uv/).
- **Npcap** installed with "WinPcap API-compatible mode" checked.
  Download from [npcap.com](https://npcap.com/).
- **Admin rights.** Required for `PROCESS_VM_READ` on the game
  process. The bot auto-relaunches itself via UAC unless you pass
  `--no-elevate`.
- **Arduino Pro Micro** (ATmega32U4) or any HID-capable board that
  speaks the bridge's serial protocol.

## Install

```
git clone <repo> RO_bot
cd RO_bot
uv sync
```

That creates `.venv/` and installs `pyserial`, `pywin32`, `scapy`.

## Arduino firmware

The HID bridge talks to the board over a USB serial port at
9600 baud. The firmware must:

- Enumerate as a HID keyboard + mouse (not just a CDC serial
  device).
- Accept single-line commands ending in `\n`:

```
M<dx>,<dy>\n        # relative mouse move, signed int16
C<button>\n         # mouse click; 1 = LEFT, 2 = RIGHT, 3 = MIDDLE
K<keycode>\n        # press + release a HID key (raw USB HID usage)
```

The keycode mapping is mirrored in `core/hid/arduino.py`
(`KEY_CODES` dict). If you use a different firmware, override that
dict — don't change the config table.

A minimal firmware reference (Arduino IDE / `HID-Project` library)
is not shipped with this repo; it was written once, flashed, and
left alone. If you need to re-flash, the key points are:

- `Keyboard.press(<usage>)` for `K` — use the HID usage page table,
  not ASCII.
- `Mouse.move(dx, dy, 0)` for `M` — keep `dx` / `dy` in the int8
  range or chunk the move client-side (the bridge already chunks).
- Serial.flush() after each command so the host can gate on
  round-trip.

## First run

1. Start the Arduino sketch (any terminal emulator on the COM port
   should echo back `OK` on `M0,0\n`).
2. Launch Ragnarok, log into your character, sit on a mob-free
   spot.
3. In a new shell:

   ```
   uv run ro-bot hunt
   ```

   First run writes `config.json` to the CWD with sensible defaults.
   Stop the bot (`0` key), open `config.json` in any text editor,
   fill in your character name, window title, mob lists, keys, and
   projection constants. COM port is detected automatically via the
   Arduino VID/PID — no config entry needed.

4. Relaunch. The bot will:
   - find the game window (matching `server.window_title`)
   - disable Windows mouse acceleration (restored on exit)
   - connect to the Arduino
   - start the sniffer on all interfaces
   - resolve memory anchors
   - enter the tick loop

## Hotkeys

| Key | Action |
|-----|--------|
| `0` | Quit |
| `p` | Pause / resume |

The hotkeys poll `GetAsyncKeyState` (global) so they work whether
the game or the console has focus.

## Troubleshooting

### "Failed to find game window"
Check `server.window_title` matches what you see in the RO client
titlebar (case-sensitive substring match). A rename on a new
patch happens from time to time.

### "No entity HP packets in 10 s"
Npcap not installed, or not in "WinPcap API-compatible" mode.
Reinstall and check the option.

### Heal never fires / fires constantly
Remember: HP comes from `0x00B0`, not memory. The sniffer cache
stays at `(0, 0)` until the first HP sync — stand still for a
few seconds on login. Threshold is a fraction (`0.30`), not a
percentage.

### Clicks miss by a fixed offset
Edit `server.projection.camera_offset_x` / `camera_offset_y` in
`config.json` — positive shifts the cursor right / down relative to
the computed cell center.
