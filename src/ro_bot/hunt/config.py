"""Runtime-immutable hunt configuration.

Built by the app layer from the loaded JSON profile (see
``app.session.BotSession``). The hunt layer consumes it read-only;
any change requires a restart. Keeping it frozen means the
controller cannot accidentally drift config during a run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ro_bot.hunt.dead_zones.zone import DeadZone


@dataclass(frozen=True)
class AimOffsetSpec:
    """Vertical aim offset in map-cell units shared by several mob names.

    Positive ``y_offset_cells`` clicks higher on screen (useful for
    flying sprites where the clickable area sits above ground cell).
    """
    names: frozenset[str]
    y_offset_cells: float


@dataclass(frozen=True)
class BuffSpec:
    """One timed consumable on the hotbar.

    Keys must be unique within the list — the hunt loop tracks the
    last-pressed timestamp per key, so two ``BuffSpec`` sharing a key
    would collapse into one timer.
    """
    key: str
    interval_sec: float


@dataclass(frozen=True)
class HealConfig:
    """Parameters for the HP heal policy.

    The policy heals whenever the current HP drops below ``min_hp``
    (an absolute value). ``hp_max`` from the sniffer is shown in
    diagnostic logs but does not influence the heal decision.

    Set ``min_hp = 0`` to disable healing entirely while keeping the
    rest of the heal block (e.g. its key) configured.

    After the emergency save teleport (HP below 50% of ``min_hp``), wait
    ``save_recovery_check_sec`` and press ``save_recovery_key`` if HP is
    still below ``min_hp`` (e.g. no potions left). ``0`` disables the check.
    """
    key: str
    min_hp: int
    cooldown_sec: float = 1.0
    save_recovery_check_sec: float = 5.0
    save_recovery_key: str = "h"


@dataclass(frozen=True)
class IdleActionConfig:
    """Teleport-after-idle parameters."""
    key: str
    after_sec: float = 10.0
    after_kill_sec: float = 2.0
    #: While the sniffer still lists a whitelisted mob name, do not count
    #: idle time toward ``after_sec`` / ``after_kill_sec`` (position may lag).
    suppress_while_visible_name: bool = True


@dataclass(frozen=True)
class DeathReturnConfig:
    """Near-death walk click (e.g. 1 HP) toward a scripted town warp cell.

    Optional ``second_delta_*`` (both set) issues a second ground click at
    first_target + (second_delta_x_cells, second_delta_y_cells).

    See :mod:`ro_bot.hunt.policies.death_return`.

    Many RO clients report **1 HP** on the death screen, not 0; keep
    ``hp_at_most`` at that value (often ``1``). Memory ``hp == 0`` is
    treated as stale / unknown, not as the normal death UI state.

    If walk clicks do not reach a manual-control town map within
    ``town_return_retry_sec``, press ``town_return_escape_key`` and repeat
    the walk clicks. ``0`` disables the retry loop.
    """
    hp_at_most: int = 1
    delta_x_cells: float = 0.0
    delta_y_cells: float = -4.7
    aim_settle_sec: float = 0.0
    second_delta_x_cells: float | None = None
    second_delta_y_cells: float | None = None
    second_click_delay_sec: float = 0.12
    town_return_retry_sec: float = 8.0
    town_return_escape_key: str = "escape"


@dataclass(frozen=True)
class OverweightConfig:
    """When carried weight is too high, press ``key`` and pause hunt/idle TP.

    ``ratio`` applies to ``weight / weight_max`` from memory
    (:class:`PlayerState`). Empty ``key`` disables the policy.
    """
    ratio: float = 0.9
    key: str = "h"
    press_interval_sec: float = 4.0


@dataclass(frozen=True)
class EscapeConfig:
    """Danger-mob teleport parameters."""
    key: str
    cooldown_sec: float = 3.0


@dataclass(frozen=True)
class FarmRouteWaypoint:
    """One cell target on a named map (RO grid coordinates)."""
    map_name: str
    x: int
    y: int


@dataclass(frozen=True)
class FarmHomeRouteConfig:
    """Ordered path from ``home_map`` to ``ReturnToFarmConfig.active_farm_map``.

    Built either from inline ``waypoints`` in the profile JSON or from
    ``compose``: an ordered list of segment names resolved via
    ``route_library.json`` (see ``app.config.route_library``).

    First waypoint must lie on ``home_map``; last must lie on the active
    farm map. The controller exempts ``home_map`` from manual-control
    suspension while this route is armed or eligible to arm.

    Set ``enabled`` false to stay fully manual in town without removing
    waypoint data from the profile.

    ``stuck_*`` — if memory shows the player cell has not changed for
    ``stuck_no_move_timeout_sec``, jiggle the HID cursor then issue a recovery
    click one grid step toward the waypoint. Earlier repeats use the same
    mouse jitter when idle exceeds ~45% of that timeout (client false rejects).

    ``finish_on_active_farm_map`` — when True, as soon as the remaining
    waypoints are all on ``active_farm_map`` and the sniffer reports that map,
    the route completes without walking to the last anchor cell (spawn
    positions on the farm often differ from a tuned ``(x,y)`` waypoint).
    """
    home_map: str
    waypoints: tuple[FarmRouteWaypoint, ...]
    enabled: bool = True
    click_cooldown_sec: float = 2.5
    #: Chebyshev distance (max of dx, dy) to count as arrived at a waypoint.
    arrival_radius_cells: int = 2
    stuck_no_move_timeout_sec: float = 1.0
    stuck_max_attempts_per_waypoint: int = 24
    #: After each 0091 map change (and when the route first arms), skip ground
    #: clicks until this many seconds pass so the client can finish loading.
    post_map_change_grace_sec: float = 3.0
    finish_on_active_farm_map: bool = True


@dataclass(frozen=True)
class HomePrepStep:
    """One HID action (optional) plus a pause before the next step.

    ``modifier_hold_clicks``: with non-empty ``hold_modifiers``, press those
    keys down, emit ``modifier_hold_clicks`` mouse clicks (see
    ``modifier_hold_mouse_button``) at the current cursor (after any
    ``click_cell`` / client click in the same step),
    ``modifier_hold_click_interval_sec`` apart, then release modifiers.
    Requires empty ``key`` (mutually exclusive with a key chord).

    ``click_cell_drag_to`` with ``click_cell_drag_repeat_count`` > 0: repeat
    an LMB drag from ``click_cell`` to ``click_cell_drag_to`` in world cells.
    If ``key`` is set, it is pressed after **each** drag (before the inter-drag
    ``click_cell_drag_repeat_interval_sec`` pause).

    ``click_client`` + ``drag_to_client`` + optional
    ``click_client_drag_repeat_count``: LMB drags in **client** pixels (HUD),
    stable when the game window moves on the desktop. ``0`` = one drag;
    ``>0`` repeats. Re-tune after resolution / skin change. Avoid a separate
    prior step that full-clicks the same ``click_client`` pixel: that click
    completes before the drag and can prevent the client from starting a drag.

    ``dismiss_chat_probe_client``: optional client pixel sampled at the **start**
    of the step (before clicks / keys). If ``max(R,G,B) >= dismiss_chat_min_channel``,
    the **white chat input** is assumed visible and ``dismiss_chat_key`` is pressed
    once (default ``escape``). Typical pattern: only on a lone ``key="space"``
    step that must not type into chat — set the probe inside the white bar when
    chat is open. Requires game ``hwnd`` in :class:`~ro_bot.hunt.policies.home_prep.HomePrepPolicy`.
    """
    key: str = ""
    delay_after_sec: float = 2.0
    #: World-map cell (projection); floats allowed (e.g. ``192.5`` for X).
    #: Mutually exclusive with ``click_client``.
    click_cell: tuple[float, float] | None = None
    #: Game client pixel (0,0 = top-left of client). For inventory UI, etc.
    click_client: tuple[int, int] | None = None
    #: With ``click_client``: LMB drag start → end in client pixels.
    drag_to_client: tuple[int, int] | None = None
    #: Client drag repeat (requires ``click_client`` + ``drag_to_client``).
    #: ``0`` runs **one** drag; ``>0`` runs that many drags (same cadence idea
    #: as ``click_cell_drag_repeat_count`` on the map).
    click_client_drag_repeat_count: int = 0
    click_client_drag_repeat_interval_sec: float = 0.25
    #: ``0`` = home-prep default before LMB down on client drags.
    click_client_drag_settle_before_down_sec: float = 0.0
    #: ``0`` = :meth:`~ro_bot.hunt.aim_service.AimService.drag_client_pixels`
    #: default segment count.
    click_client_drag_segments: int = 0
    hold_modifiers: tuple[str, ...] = ()
    #: Mouse clicks while ``hold_modifiers`` are held (0 = off).
    modifier_hold_clicks: int = 0
    modifier_hold_click_interval_sec: float = 0.25
    #: ``"left"`` or ``"right"`` (firmware must implement ``RD``/``RU``).
    modifier_hold_mouse_button: str = "left"
    #: World-map LMB drag end (requires ``click_cell`` and repeat count > 0).
    click_cell_drag_to: tuple[float, float] | None = None
    click_cell_drag_repeat_count: int = 0
    click_cell_drag_repeat_interval_sec: float = 0.25
    #: Client pixel for chat-bar brightness probe (see class docstring).
    dismiss_chat_probe_client: tuple[int, int] | None = None
    dismiss_chat_min_channel: int = 228
    dismiss_chat_key: str = "escape"


@dataclass(frozen=True)
class HomePrepConfig:
    """Town-side restock / storage sequence before :class:`FarmHomeRoutePolicy`."""
    enabled: bool = True
    steps: tuple[HomePrepStep, ...] = ()
    post_steps: tuple[HomePrepStep, ...] = ()
    #: When > 0, wait until ``weight / weight_max`` drops below this ratio.
    finish_when_weight_ratio_below: float = 0.0
    max_total_sec: float = 180.0


@dataclass(frozen=True)
class FarmTransition:
    """One neighbor-map escape → farm-map recovery rule.

    Interpretation: if we detect ourselves on ``neighbor_map``, walk
    ``direction`` for ``ReturnToFarmConfig.walk_cells`` cells to step
    back into a warp that returns to ``farm_map``.

    Directions are compass-style on the RO map grid: ``up`` = +Y
    (north), ``right`` = +X (east).
    """
    farm_map: str
    neighbor_map: str
    direction: str  # "left" | "right" | "up" | "down"


@dataclass(frozen=True)
class ReturnToFarmConfig:
    """Return-to-farm-map policy tunables.

    The policy listens for map changes. When the new map is listed as a
    neighbor of some farm map in ``transitions``, it waits
    ``settle_sec`` (so the client has a position to read), then issues
    a walk-click in the configured direction. If after ``retry_sec`` we
    are still on the same neighbor map, it tries again — up to
    ``max_retries`` attempts, each aimed at a slightly different cell
    so a misaligned warp can still be hit. The retry sequence is:

      1. ``walk_cells`` straight along the direction (base).
      2. Same distance, 1 cell to the left (CCW perpendicular from
         the direction vector).
      3. Same distance, 1 cell to the right.
      4. ``walk_cells + 1`` along the direction.

    Attempts beyond step 4 disarm the policy with a warning.

    ``active_farm_map`` (optional) fixes ambiguity when several farm maps
    share neighbors (e.g. ``cmd_fild01`` ↔ ``um_fild03``). Only transitions
    whose ``farm_map`` equals this value are considered: walk-back runs when
    you land on a **neighbor** of that farm, and never when the current map
    **is** that farm. Omit or leave empty for legacy behavior (single global
    lookup by neighbor name — fragile if one neighbor appears in multiple
    blocks).

    ``home_route`` (optional) runs :class:`FarmHomeRoutePolicy`: click path
    from ``home_map`` through any intermediate maps to the final cell on
    ``active_farm_map``. Requires a non-empty ``active_farm_map``.

    ``home_navigation_enabled`` — when false, ``home_route`` is cleared at
    session build (no town→farm clicks); use while recording a path manually.
    JSON ``home_route`` is ignored while disabled. Neighbor walk-back still
    follows ``maps`` unless you clear those transitions.

    ``home_prep`` (optional) runs :class:`~ro_bot.hunt.policies.home_prep.HomePrepPolicy`
    on ``home_route.home_map`` before waypoint navigation; requires
    ``home_route`` and non-empty ``steps`` when enabled.
    """
    walk_cells: int = 10
    settle_sec: float = 1.5
    #: Minimum wait after a map change before walk-back clicks (with settle_sec).
    post_map_change_grace_sec: float = 3.0
    retry_sec: float = 5.0
    max_retries: int = 4
    transitions: tuple[FarmTransition, ...] = ()
    #: When set, only return toward this farm map; standing on this map
    #: never arms walk-back.
    active_farm_map: str | None = None
    home_route: FarmHomeRouteConfig | None = None
    #: Town→farm waypoint navigation (registry or JSON ``home_route``).
    home_navigation_enabled: bool = True
    home_prep: HomePrepConfig | None = None
    #: Optional override; registry merges from :class:`FarmReturnPlan` when empty.
    farm_arrival_steps: tuple[HomePrepStep, ...] = ()


@dataclass(frozen=True)
class EngagementConfig:
    """Tunables for the engage / re-aim state machine.

    ``path_stuck_*`` controls early abandonment of unreachable distant
    targets: if we engage a mob ``>= path_stuck_min_dist`` cells away
    and the player has not moved a single cell within
    ``path_stuck_timeout_sec``, the click was clearly rejected (path
    blocked / mob already gone). Blacklist short and look for another
    candidate immediately instead of waiting the full
    ``kill_timeout_sec``. Set ``path_stuck_min_dist <= 0`` to disable.

    ``dead_zone_wait_sec`` limits how long we trust "candidate is behind
    HUD, wait for it to walk out". If no non-dead-zone candidate appears
    within this window, the controller falls back to idle teleport.

    ``approach_stall_*`` handles melee / ledge cases: the player moved
    toward the mob but has stood still on one cell for
    ``approach_stall_timeout_sec`` while the mob remains at least
    ``approach_stall_min_dist`` away. Disabled when
    ``approach_stall_timeout_sec <= 0``.

    ``ks_guard_*`` skips (and abandons) targets that are still
    ``>= ks_guard_min_dist`` away but already have
    ``max_hp - hp >= ks_guard_min_hp_deficit`` (someone else is hitting
    them). Disabled when ``ks_guard_min_dist <= 0``.

    ``player_closer_*`` skips (and abandons) when another visible player
    is at least ``player_closer_margin`` cells closer to the mob
    (Manhattan), or when any player is within ``player_near_mob_radius``
    cells of the mob regardless of who is closer. Positions come from
    sniffer stop-move packets. Disabled when ``player_closer_margin < 0``
    and ``player_near_mob_radius <= 0``.

    ``player_gid_min`` / ``player_gid_max`` delimit the player account-ID
    range (on this server commonly 3 000 000–4 000 000). Any entity
    whose GID falls in ``[player_gid_min, player_gid_max)`` with a known
    map cell is treated as another player for ``player_closer_*``, even
    when the 0x0A30 name has not arrived yet. Set ``player_gid_max`` to
    ``0`` to disable the GID range and fall back to the name-only
    heuristic.

    ``player_visible_retp_sec``: after idle teleport on a hunt map
    (same map name, new coordinates), keep re-teleporting while any
    other player remains visible. ``0`` disables the post-TP scan only.

    ``player_defer_hunt_if_visible``: when true, never start a new
    engagement while any other player is visible — idle teleport instead
    (KS avoidance takes priority over farming).

    ``all_blacklisted_force_tp_sec`` breaks the "loop forever on the
    only visible target" deadlock: when every visible whitelisted name
    is in the GID blacklist (typically because the same unreachable mob
    has timed out one or more times in a row), force an idle teleport
    after this many seconds instead of waiting out the blacklist and
    immediately re-engaging the same mob again. ``0`` disables.

    ``abandon_target_key`` — optional single keypress after these
    abandonments (and KS abandon) to clear target in-game; omit or "" to
    skip.
    """
    kill_timeout_sec: float = 15.0
    blacklist_sec: float = 30.0
    reaim_click_cooldown_sec: float = 0.3
    #: When the mob has not moved and the player is within this many cells,
    #: skip LMB re-clicks (prevents 1-cell walk jitter). Skill mode uses
    #: ``engage_skill_repeat_sec`` instead.
    reaim_hold_dist: int = 3
    aim_settle_sec: float = 0.10
    target_settle_sec: float = 2.5
    path_stuck_min_dist: int = 5
    path_stuck_timeout_sec: float = 1.5
    path_stuck_blacklist_sec: float = 5.0
    dead_zone_wait_sec: float = 3.0
    approach_stall_timeout_sec: float = 2.5
    approach_stall_min_dist: int = 3
    approach_stall_blacklist_sec: float = 5.0
    ks_guard_min_dist: int = 3
    ks_guard_min_hp_deficit: int = 1
    ks_guard_blacklist_sec: float = 30.0
    player_closer_margin: int = 3
    player_near_mob_radius: int = 45
    #: Skip hunt when any other player is within this many cells of the bot.
    player_near_bot_radius: int = 40
    player_closer_max_mob_dist: int = 0
    player_closer_max_player_mob_dist: int = 60
    player_closer_blacklist_sec: float = 30.0
    player_closer_force_tp: bool = True
    #: When true, do not start new engagements while any other player is
    #: visible on the map (GID range + cell). Prefer idle teleport over KS.
    player_defer_hunt_if_visible: bool = True
    #: After the last sighting of another player, keep deferring hunt for this
    #: many seconds (covers sniffer gaps and standing-still players).
    player_visible_grace_sec: float = 25.0
    #: After idle teleport on a hunt map (same map, new coords), keep
    #: re-teleporting while other players remain visible. ``0`` disables
    #: the post-TP scan (``player_defer_hunt_if_visible`` still applies).
    player_visible_retp_sec: float = 5.0
    player_gid_min: int = 3_000_000
    player_gid_max: int = 4_000_000
    all_blacklisted_force_tp_sec: float = 5.0
    abandon_target_key: str | None = None
    #: While the player is within this Manhattan distance of a mob stack,
    #: do not queue idle warp after abandonments (client may be fighting
    #: a co-located sprite).
    stack_cell_melee_dist: int = 2
    #: Remember a preferred GID / cell for this long after stack combat.
    stack_cell_resume_sec: float = 30.0
    #: After this many abandons on the same cell without a kill, force idle
    #: warp before re-engaging. ``0`` disables the ladder.
    stack_cell_warp_after_abandons: int = 3
    #: Hotbar key pressed before every engage / re-aim click (e.g. ``"w"``).
    #: When set, each attack cycle is key + LMB target click until the mob dies.
    engage_skill_key: str | None = None
    #: Pause after ``engage_skill_key`` before the aim click (seconds).
    engage_skill_delay_sec: float = 0.05
    #: In skill mode, min seconds between recasts on a stationary in-range mob.
    engage_skill_repeat_sec: float = 1.5


@dataclass(frozen=True)
class HuntConfig:
    """All per-profile hunt settings.

    Built from the JSON profile in ``app.session.BotSession``. The
    controller treats this as read-only; edit ``config.json`` and
    restart to change any field.
    """
    char_name: str
    allowed_names: frozenset[str] = field(default_factory=frozenset)
    dangerous_names: frozenset[str] = field(default_factory=frozenset)
    #: Maps where hunt automation is suspended (manual player control).
    #: On these maps the controller behaves like pause: no attack, no
    #: teleport, no automated actions.
    manual_control_maps: frozenset[str] = field(default_factory=frozenset)
    dead_zones: tuple[DeadZone, ...] = ()
    engagement: EngagementConfig = field(default_factory=EngagementConfig)
    heal: HealConfig | None = None
    death_return: DeathReturnConfig | None = None
    idle_action: IdleActionConfig | None = None
    overweight: OverweightConfig | None = None
    escape: EscapeConfig | None = None
    return_to_farm: ReturnToFarmConfig | None = None
    buffs: tuple[BuffSpec, ...] = ()
    aim_offsets: tuple[AimOffsetSpec, ...] = ()
    #: Accept every mob name in targeting (ignore ``allowed_names``).
    target_all_mobs: bool = False
    #: Heal/buff on any map with a known name (ignore town blacklist).
    ignore_map_restrictions: bool = False
