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
    """Parameters for the HP-threshold heal policy.

    ``min_hp`` is an absolute fallback used only when the sniffer
    cannot observe ``SP_MAXHP`` (some private servers / Gepard builds
    never emit it). When ``hp_max == 0``, the policy heals as soon as
    current HP drops below ``min_hp``. With a known ``hp_max`` the
    percentage threshold takes over and ``min_hp`` is ignored.
    """
    key: str
    threshold_pct: float = 0.30
    cooldown_sec: float = 1.0
    min_hp: int = 500


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
class EngagementConfig:
    """Tunables for the engage / re-aim state machine."""
    kill_timeout_sec: float = 15.0
    blacklist_sec: float = 30.0
    reaim_click_cooldown_sec: float = 0.3
    aim_settle_sec: float = 0.10
    target_settle_sec: float = 2.5


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
    buffs: tuple[BuffSpec, ...] = ()
