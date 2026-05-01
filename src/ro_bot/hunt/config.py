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
    """
    walk_cells: int = 10
    settle_sec: float = 1.5
    retry_sec: float = 5.0
    max_retries: int = 4
    transitions: tuple[FarmTransition, ...] = ()


@dataclass(frozen=True)
class EngagementConfig:
    """Tunables for the engage / re-aim state machine.

    ``stuck_timeout_threshold`` counts cumulative timeouts on the same
    GID since the last kill / map change. Once reached, the GID is
    blacklisted for ``stuck_blacklist_sec`` instead of the usual
    ``blacklist_sec`` so the idle-action timer can run out and trigger
    a teleport (otherwise the short blacklist window keeps re-engaging
    an unreachable mob forever). Set threshold ``<= 0`` to disable.
    """
    kill_timeout_sec: float = 15.0
    blacklist_sec: float = 30.0
    reaim_click_cooldown_sec: float = 0.3
    aim_settle_sec: float = 0.10
    target_settle_sec: float = 2.5
    stuck_timeout_threshold: int = 3
    stuck_blacklist_sec: float = 300.0


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
    allowed_maps: frozenset[str] = field(default_factory=frozenset)
    dead_zones: tuple[DeadZone, ...] = ()
    engagement: EngagementConfig = field(default_factory=EngagementConfig)
    heal: HealConfig | None = None
    idle_action: IdleActionConfig | None = None
    escape: EscapeConfig | None = None
    return_to_farm: ReturnToFarmConfig | None = None
    buffs: tuple[BuffSpec, ...] = ()
