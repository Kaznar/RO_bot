# Hunt state machine

The hunt controller is a **single-threaded tick loop**. Each tick is a
short snapshot of the world (player pos, visible mobs, HP from
sniffer) followed by one HID action (a click, a key press, or
nothing). Policies are pure-ish objects that own their own cooldown
state.

## Tick pipeline

```
tick():
  1. drain EventBus  → forget died / lost GIDs, reset on map change
  2. read player pos + HP_cur / HP_max
  3. heal policy     (if HP < min_hp, press heal key)
  4. buffs policy    (refresh each configured buff at its interval)
  5. escape policy   (if any mob from `dangerous` is visible → teleport)
  6. if engaged:
       continue_engagement
         ├─ target died      → mark KILL, go to 7
         ├─ target vanished  → blacklist + back to idle
         ├─ kill_timeout     → blacklist + back to idle
         ├─ path stuck       → blacklist short, mark "force teleport
         │                     on next no-candidates", go to 7
         └─ target settled in a new cell → reaim (subject to click cooldown)
  7. else / idle:
       targeting.collect_candidates(sniffer ∪ tracker, blacklist, dead_zones)
       if candidates:
         engagement.engage(targeting.pick_nearest(candidates, player_pos))
       else:
         idle_action — fire teleport immediately if "force teleport"
                       was set by path-stuck, otherwise after `after_sec`
  8. return suggested sleep (`IDLE_POLL_SEC` or `ENGAGED_POLL_SEC`)
```

Constants live in `hunt/constants.py`; per-profile knobs live in
`HuntConfig` (hydrated from `config.json` by the app layer).

## Engagement FSM

```
            ┌───────────── IDLE ─────────────┐
            │                                │
 pick_nearest                          no_candidates
            │                                │
            ▼                                │
       CLICKING (first aim + click)          │
            │                                │
            │   target settles new cell      │
            │   & reaim_click_cooldown_sec ok│
            ▼                                │
       ENGAGED ◄───── reaim ─────┐           │
            │                    │           │
            │ target died / vanish / timeout │
            └────────────────────────────────┘
```

- `aim_settle_sec` — wait between moving the cursor and the physical
  click (Arduino HID does not settle instantly).
- `target_settle_sec` — how long a mob must sit in the same 1-cell
  before we consider it safe to click. Cell hops within 0.5 s of the
  last hop are treated as a single "burst" move (the timer counts
  from the start of the burst), so multi-cell walks don't starve
  engagement.
- `reaim_click_cooldown_sec` — minimum delay between consecutive
  clicks on the same mob when it moves.
- `blacklist_sec` — GID is muted after a kill_timeout; prevents the
  same stuck mob from hogging the loop.
- `kill_timeout_sec` — if engaged too long without a `0x0080` vanish
  or HP = 0, treat as stuck and re-enter IDLE.
- `path_stuck_*` — early abandonment: if the engaged mob is at least
  `min_dist` cells away and the player has not moved a single cell
  within `timeout_sec`, the click was rejected (path blocked / mob
  already gone). Blacklist short and bypass idle grace on the next
  no-candidates pass.
- `approach_stall_*` — if the player stops on one cell while the mob’s
  settled cell is still ≥ `approach_stall_min_dist` away for
  `approach_stall_timeout_sec`, abandon (common melee / height /
  ledge failure mode).
- `ks_guard_*` — do not target (and abandon if already chasing) mobs
  that are still ≥ `ks_guard_min_dist` away but already damaged
  (`max_hp - hp` ≥ threshold), to reduce kill-steal appearances.

## Policies (all in `src/ro_bot/hunt/policies/`)

| Policy | Inputs | Effect |
|--------|--------|--------|
| `heal` | sniffer HP, `HealConfig` | Presses heal key when `hp < min_hp`, respects `cooldown_sec`. |
| `buffs` | `list[BuffSpec]`, map name | Rotates buff presses on `interval_sec` each; skipped off-map. |
| `idle_action` | last-candidate timestamp, last-kill timestamp | Presses teleport after `after_sec` idle or `after_kill_sec` post-kill. Can be force-fired by path-stuck. |
| `overweight` | memory weight / max | At ≥ `ratio` load: press `key` on interval, suspend hunt + idle TP until lighter. |
| `escape` | sniffer snapshot, `dangerous` mob list | Teleports on first sight; cooldown prevents key spam. |
| `targeting` | sniffer + tracker snapshot, blacklist, dead zones, cell observer | Returns nearest settled, non-masked candidate; optional KS HP/dist filter. |
| `engagement` | targeting result, aim service, click cooldown | Drives CLICKING → ENGAGED → back to IDLE. |
| `path_stuck` | engagement target state, current player cell | Detects rejected engage clicks on distant targets (player not moving) and abandons them after `path_stuck_timeout_sec`. |
| `approach_stall` | engagement state, player vs settled mob distance | Abandons when the player stalls on one tile but the mob is still too far (Manhattan). |
| `remote_contested` | sniffer entity HP vs max_hp, distance | Abandons engaged targets that match the KS guard; same rule filters `collect_candidates`. |
| `return_to_farm` | map change events, `walk_cells`/direction config | When the bot lands on a configured neighbor map, walks back through the warp toward the farm map (with retry jitter). |

## Pause / resume

Hotkey `p` toggles pause. Pause captures the current monotonic time;
resume replays the delta into every policy timestamp via
`PauseToken.shift(ts)`, so cooldowns continue where they stopped —
not from zero.

## Map changes

When you leave a **hunt** map (not in `manual_control_maps`) for a
**manual-control** map (town, storage, …) and later return to that same
hunt map, the controller queues one **idle teleport** (`profile.idle_action.key`,
usually `t`) on the first hunt tick **before** targeting — so you do not
immediately click a mob that may be standing on the warp tile (avoid
engage / idle / escape loops). Transitions use the **previous → new**
map names from each 0x0091 callback (not a tick-delayed snapshot), so
rapid town↔farm hops still match correctly.

When ``return_to_farm.active_farm_map`` is set, the same idle teleport
queues on **neighbor → that farm** edges listed under that farm in
``return_to_farm.maps`` (e.g. ``cmd_fild01`` → ``um_fild03`` after a
return-to-farm walk), so the bot does not immediately engage on the
warp tile.

0x0091 ZC_NPCACK_MAPMOVE clears:

- the sniffer entity cache,
- the tracker GID → address map,
- `EngagementMachine` state (no longer engaged),
- the blacklist (GIDs are session-unique; carrying them across maps
  would only delay re-engagement of mobs the new map happens to
  reuse),
- the cell observer (settle timestamps would be stale anyway),
- the path-stuck "force teleport" flag.

The `idle_action` timer is reset (the post-map idle window starts
fresh). Heal and buff timers survive — buffs simply skip themselves
on non-allowed maps. The `return_to_farm` policy gets a map_change
notification and may trigger a walk-back if the new map is a
configured neighbor.
