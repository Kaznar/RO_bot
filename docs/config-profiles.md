# Config & profiles (SQLite)

All configuration lives in `profiles.db` (SQLite). The DB file is
committed to `.gitignore` — you create it locally and edit it with
[DB Browser for SQLite](https://sqlitebrowser.org/). There is no CRUD
CLI.

## Tables overview

Two object families:

- **Server** — properties of a client/server combo: process name,
  window title, pixel-per-cell projection, HUD dead zones.
- **Profile** — per-character farming strategy: character name,
  primary map, mob whitelist / dangerous list, buffs, heal, idle
  teleport, escape.

```
server ─┬─ server_projection      (1:1)
        └─ server_dead_zone       (1:N)

profile ─┬─ server               (N:1, shared across profiles)
         ├─ profile_engagement   (1:1, cooldowns & settle times)
         ├─ profile_heal         (1:1)
         ├─ profile_idle_action  (1:1)
         ├─ profile_escape       (1:1)
         ├─ profile_mob          (1:N, role = allowed | dangerous)
         ├─ profile_map          (1:N, allowed maps for buffs / heal)
         └─ profile_buff         (1:N, ordered, with interval_sec)
```

Full `CREATE TABLE` statements live in
[`src/ro_bot/app/db/schema.sql`](../src/ro_bot/app/db/schema.sql) —
that is the source of truth; this document only explains the model.

## Field reference (non-obvious fields)

### `server_projection`
- `px_per_cell_x` / `px_per_cell_y` — pixels per map cell at the
  zoom level you play at. Used to translate in-game coordinates to
  screen pixels. Calibrate by hand in DB Browser (known-location
  mob + measure cursor offset).
- `camera_offset_x/y` — fine-tune shift in pixels if the cursor lands
  consistently off-center.

### `server_dead_zone`
- `anchor` — one of `TL` / `TR` / `BL` / `BR`. Zone is measured from
  that corner of the client area.
- `inset_x/y` + `width/height` — rectangle. Any cell projected into
  this rect is ignored by targeting (HUD overlay, chat box, skill
  bar, etc.).

### `profile_engagement`
All tunable timers in seconds. Defaults are conservative:

| Column | Default | Meaning |
|--------|---------|---------|
| `kill_timeout_sec` | 10.0 | Max time stuck on one GID before giving up. |
| `blacklist_sec` | 30.0 | How long a problematic GID is ignored. |
| `reaim_click_cooldown_sec` | 0.3 | Min delay between consecutive clicks on same mob. |
| `aim_settle_sec` | 0.10 | Sleep between cursor move and click. |
| `target_settle_sec` | 2.5 | How long mob must sit in a cell before we click. |

### `profile_heal`
- `key` — must match `KEY_CODES` in `core/hid/arduino.py` (e.g.
  `F1`, `'1'`, `'\ '`). Unknown keys fail at session start.
- `threshold_pct` — float `0.0–1.0`.

### `profile_idle_action`
- `after_sec` — no candidates for this long → press `key`.
- `after_kill_sec` — same but after last kill, typically smaller for
  "tp after kill" playstyles.

### `profile_buff`
- `order_index` — UI ordering and ties in scheduling.
- `interval_sec` — buff re-press cadence; seconds, not ticks.

### `profile_mob.role`
- `allowed` — whitelist. Everything else on screen is ignored.
- `dangerous` — escape policy teleports immediately on sight.

## Editing workflow

1. Close the bot.
2. Open `profiles.db` in DB Browser. Write-to-DB mode.
3. Edit the row(s). Save + close.
4. Relaunch the bot. `BotSession.start()` re-reads everything.

## Adding a new server / profile

- **New server row** — insert into `server`, then `server_projection`
  (always), and `server_dead_zone` (one row per HUD rectangle).
- **New profile row** — insert into `profile` with `server_id`,
  then the 1:1 siblings (`profile_engagement`, `profile_heal`,
  `profile_idle_action`, `profile_escape`), then the 1:N rows
  (`profile_mob`, `profile_map`, `profile_buff`).
- Wrap related inserts in a transaction (DB Browser → *Write Changes*).

Missing 1:1 rows will be reported by `ProfileRepository` with an
explicit `ProfileNotFoundError` / schema error. Add them, retry.

## Schema evolution

- Bump `PRAGMA user_version` and add a migration step in
  `src/ro_bot/app/db/migrations.py`.
- See `.cursor/rules/sqlite-profiles.mdc` — no JSON blobs inside
  columns, normalize instead (one row per value).
