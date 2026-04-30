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
         ├─ target died    → mark KILL, go to 7
         ├─ target vanished → blacklist + back to idle
         └─ target settled in a new cell → reaim (subject to click cooldown)
  7. else / idle:
       idle_action policy (teleport after N seconds of no candidates)
       targeting.collect_candidates(sniffer ∪ tracker, blacklist, dead_zones)
       targeting.pick_nearest(candidates, player_pos)
       engagement.engage(target)
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
  before we consider it safe to click. Prevents cursor-chasing.
- `reaim_click_cooldown_sec` — minimum delay between consecutive
  clicks on the same mob when it moves.
- `blacklist_sec` — GID is muted after a timeout or an unreachable
  click; prevents the same stuck mob from hogging the loop.
- `kill_timeout_sec` — if engaged too long without a `0x0080` vanish
  or HP = 0, treat as stuck and re-enter IDLE.

## Policies (all in `src/ro_bot/hunt/policies/`)

| Policy | Inputs | Effect |
|--------|--------|--------|
| `heal` | sniffer HP, `HealConfig` | Presses heal key when `hp < min_hp`, respects `cooldown_sec`. |
| `buffs` | `list[BuffSpec]`, map name | Rotates buff presses on `interval_sec` each; skipped off-map. |
| `idle_action` | last-candidate timestamp, last-kill timestamp | Presses teleport after `after_sec` idle or `after_kill_sec` post-kill. |
| `escape` | sniffer snapshot, `dangerous` mob list | Teleports on first sight; cooldown prevents key spam. |
| `targeting` | sniffer + tracker snapshot, blacklist, dead zones, cell observer | Returns nearest settled, non-masked candidate. |
| `engagement` | targeting result, aim service, click cooldown | Drives CLICKING → ENGAGED → back to IDLE. |

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
- the blacklist is kept (mob names survive teleports).

Heal, buffs and idle timers survive map changes.
