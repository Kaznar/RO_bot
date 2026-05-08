# Config

All configuration lives in a single JSON file, `config.json` by
default. The file is committed to `.gitignore` — the bot creates it
from sensible defaults on first run, then you edit it in any text
editor.

## Location

- Default: `./config.json` (project root / working directory).
- Override: `--config path/to/other.json`.

## First run

If the path does not exist, the loader writes the contents of
`ro_bot/app/config/defaults.py` to it and logs:

```
WARNING  No config found — created defaults at config.json.
         Edit it (char_name, window_title, mobs, ...) then relaunch.
```

The bot continues booting; it will almost certainly fail at the
window-detection step until you edit at least `server.window_title`
and `profile.char_name`.

## Shape

```json
{
  "server": {
    "name": "nexusro",
    "process_name": "nexusro.exe",
    "window_title": "NexusRO",
    "projection": {
      "px_per_cell_x": 42.0,
      "px_per_cell_y": 39.0,
      "camera_offset_x": 0.0,
      "camera_offset_y": 0.0
    },
    "dead_zones": [
      {"anchor": "TL", "inset_x": 0, "inset_y": 0,
       "width": 220, "height": 70},
      {"anchor": "TR", "inset_x": 130, "inset_y": 0,
       "width": 150, "height": 60}
    ]
  },
  "profile": {
    "char_name": "JoJo",
    "manual_control_maps": ["prontera", "payon"],
    "mobs": {
      "allowed": ["Muka", "Porcellio"],
      "dangerous": ["Hunter Fly"]
    },
    "engagement": {
      "kill_timeout_sec": 15.0,
      "blacklist_sec": 30.0,
      "reaim_click_cooldown_sec": 0.3,
      "aim_settle_sec": 0.10,
      "target_settle_sec": 2.5,
      "path_stuck_min_dist": 5,
      "path_stuck_timeout_sec": 1.5,
      "path_stuck_blacklist_sec": 5.0
    },
    "heal": {
      "key": "q",
      "min_hp": 500,
      "cooldown_sec": 1.0
    },
    "idle_action": {
      "key": "t",
      "after_sec": 10.0,
      "after_kill_sec": 2.0
    },
    "escape": {
      "key": "t",
      "cooldown_sec": 3.0
    },
    "buffs": [
      {"order": 1, "key": "f", "interval_sec": 1800.0},
      {"order": 2, "key": "c", "interval_sec": 1200.0}
    ],
    "return_to_farm": {
      "walk_cells": 10,
      "settle_sec": 1.5,
      "retry_sec": 5.0,
      "max_retries": 4,
      "maps": {
        "cmd_fild01": {
          "beach_dun3": "right",
          "cmd_fild03": "left",
          "cmd_fild02": "up"
        }
      }
    }
  }
}
```

## Field reference (non-obvious fields)

### `server.projection`

- `px_per_cell_x` / `px_per_cell_y` — pixels per map cell at the
  zoom level you play at. Used to translate in-game coordinates to
  screen pixels. Calibrate by hand (known-location mob + measure
  cursor offset).
- `camera_offset_x` / `camera_offset_y` — fine-tune shift in pixels
  if the cursor lands consistently off-center. Optional; default 0.

### `server.dead_zones`

- `anchor` — one of `TL` / `TR` / `BL` / `BR`. Zone is measured from
  that corner of the client area.
- `inset_x` / `inset_y` + `width` / `height` — rectangle. Any cell
  projected into this rect is ignored by targeting (HUD overlay,
  chat box, skill bar, etc.).

### `profile.engagement`

All tunable timers in seconds. Defaults are conservative:

| Field | Default | Meaning |
|--------|---------|---------|
| `kill_timeout_sec` | 15.0 | Max time stuck on one GID before giving up. |
| `blacklist_sec` | 30.0 | How long a problematic GID is ignored. |
| `reaim_click_cooldown_sec` | 0.3 | Min delay between consecutive clicks on same mob. |
| `aim_settle_sec` | 0.10 | Sleep between cursor move and click. |
| `target_settle_sec` | 2.5 | How long mob must sit in a cell before we click. Burst-walks (cell hops within 0.5 s) are merged so the timer counts from the start of a multi-cell burst. |
| `path_stuck_min_dist` | 5 | Distance (cells) above which path-stuck detection arms. `0` disables. |
| `path_stuck_timeout_sec` | 1.5 | If the player hasn't moved a single cell within this window after engaging a distant mob, the click was rejected — abandon the target early. |
| `path_stuck_blacklist_sec` | 5.0 | Short blacklist after path-stuck abandonment. Followed by an immediate teleport when no other candidate is reachable. |

### `profile.heal`

- `key` — must match `KEY_CODES` in `core/hid/arduino.py` (e.g.
  `"F1"`, `"1"`, `" "`). Unknown keys fail at session start.
- `min_hp` — required int. Heal key fires when current HP drops
  below this value. Set to `0` to keep the block configured but
  disable the policy.
- `cooldown_sec` — optional float, defaults to `1.0`. Minimum gap
  between consecutive heal presses.

Omit the whole `heal` block to disable the heal policy.

### `profile.idle_action`

- `after_sec` — no candidates for this long → press `key`.
- `after_kill_sec` — same but after last kill, typically smaller for
  "tp after kill" playstyles.

Omit the whole block to disable.

### `profile.escape`

- `key` — key to press when a `dangerous` mob appears.
- `cooldown_sec` — minimum seconds between escape key presses.

Omit the whole block to disable.

### `profile.buffs`

List of `{order, key, interval_sec}` entries.

- `order` — ties in scheduling, lower goes first.
- `key` — hotbar key to press.
- `interval_sec` — buff re-press cadence; seconds.

### `profile.mobs`

- `allowed` — whitelist. Everything else on screen is ignored.
- `dangerous` — `escape` policy teleports immediately on sight.

### `profile.manual_control_maps`

- List of map names where automation is suspended.
- On these maps the hunt controller behaves like pause: no attack, no
  teleport, no heal/buff presses, no return-to-farm walk.
- Use this for towns, market maps, and any place where you want full
  manual control.

### `profile.return_to_farm`

Walks back into a warp when the bot accidentally steps onto a
neighbor map. Disabled (policy not created) if the block is omitted
or `maps` is empty.

| Field | Default | Meaning |
|-------|---------|---------|
| `walk_cells` | `10` | Distance in map cells to click from the player, in the configured direction. |
| `settle_sec` | `1.5` | Delay after the map change before the first click (gives the client time to load player position). |
| `retry_sec` | `5.0` | If still on the neighbor map after this many seconds, click again. |
| `max_retries` | `4` | Maximum clicks before giving up (capped by the 4-step jitter sequence below). |
| `maps` | `{}` | `farm_map → {neighbor_map: direction}` — one entry per neighbor. |

**Retry jitter sequence.** Each retry aims at a slightly different
cell so a warp that isn't perfectly under the base target still gets
hit:

1. Base — `walk_cells` straight along the direction.
2. 1 cell to the **left** (CCW-rotated perpendicular from the walking direction).
3. 1 cell to the **right** (CW-rotated perpendicular).
4. `walk_cells + 1` straight along the direction.

If `max_retries` is lower than 4, later variants simply don't fire.
Higher values are capped at 4 (the sequence doesn't loop).

Directions are `"left"` / `"right"` / `"up"` / `"down"` (compass on
the map grid: `up` = +Y = north).

Each `neighbor_map` must be unique across all farm maps — a map can
only be a neighbor of one farm.

**Notes:**

- If you deliberately want to leave your farm map (e.g. to restock),
  pause the bot first. Otherwise it will walk you straight back.
- Neighbor maps should usually be listed in `manual_control_maps` if
  you want to navigate there manually without bot actions.
- Escape (dangerous mob) still takes priority over the return walk.

## Editing workflow

1. Close the bot.
2. Open `config.json` in any editor. It is just JSON.
3. Save + close.
4. Relaunch the bot. `run_hunt` re-reads the file on every start.

## Schema evolution

- New fields should come with a sensible default so older configs
  keep loading without edits.
- Extend `ro_bot/app/config/defaults.py` and the relevant parser in
  `ro_bot/app/config/loader.py`.
- Breaking changes (renaming a field, changing types) require a
  manual migration — or just delete your `config.json` and let the
  bot regenerate defaults, then re-customize.
