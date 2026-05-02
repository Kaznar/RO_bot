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

## Policies (all in `src/ro_bot/hunt/policies/`)

| Policy | Inputs | Effect |
|--------|--------|--------|
| `heal` | sniffer HP, `HealConfig` | Presses heal key when `hp < min_hp`, respects `cooldown_sec`. |
| `buffs` | `list[BuffSpec]`, map name | Rotates buff presses on `interval_sec` each; skipped off-map. |
| `idle_action` | last-candidate timestamp, last-kill timestamp | Presses teleport after `after_sec` idle or `after_kill_sec` post-kill. Can be force-fired by path-stuck. |
| `escape` | sniffer snapshot, `dangerous` mob list | Teleports on first sight; cooldown prevents key spam. |
| `targeting` | sniffer + tracker snapshot, blacklist, dead zones, cell observer | Returns nearest settled, non-masked candidate. |
| `engagement` | targeting result, aim service, click cooldown | Drives CLICKING → ENGAGED → back to IDLE. |
| `path_stuck` | engagement target state, current player cell | Detects rejected engage clicks on distant targets (player not moving) and abandons them after `path_stuck_timeout_sec`. |
| `return_to_farm` | map change events, `walk_cells`/direction config | When the bot lands on a configured neighbor map, walks back through the warp toward the farm map (with retry jitter). |

## Pause / resume

Hotkey `p` toggles pause. Pause captures the current monotonic time;
resume replays the delta into every policy timestamp via
`PauseToken.shift(ts)`, so cooldowns continue where they stopped —
not from zero.

## Map changes

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
