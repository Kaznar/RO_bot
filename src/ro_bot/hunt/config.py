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
    """
    key: str
    min_hp: int
    cooldown_sec: float = 1.0


@dataclass(frozen=True)
class IdleActionConfig:
    """Teleport-after-idle parameters."""
    key: str
    after_sec: float = 10.0
    after_kill_sec: float = 2.0


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
    """
    walk_cells: int = 10
    settle_sec: float = 1.5
    retry_sec: float = 5.0
    max_retries: int = 4
    transitions: tuple[FarmTransition, ...] = ()
    #: When set, only return toward this farm map; standing on this map
    #: never arms walk-back.
    active_farm_map: str | None = None


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

    ``abandon_target_key`` — optional single keypress after these
    abandonments (and KS abandon) to clear target in-game; omit or "" to
    skip.
    """
    kill_timeout_sec: float = 15.0
    blacklist_sec: float = 30.0
    reaim_click_cooldown_sec: float = 0.3
    aim_settle_sec: float = 0.10
    target_settle_sec: float = 2.5
    path_stuck_min_dist: int = 5
    path_stuck_timeout_sec: float = 1.5
    path_stuck_blacklist_sec: float = 5.0
    dead_zone_wait_sec: float = 3.0
    approach_stall_timeout_sec: float = 2.5
    approach_stall_min_dist: int = 3
    approach_stall_blacklist_sec: float = 5.0
    ks_guard_min_dist: int = 0
    ks_guard_min_hp_deficit: int = 1
    ks_guard_blacklist_sec: float = 8.0
    abandon_target_key: str | None = None


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
