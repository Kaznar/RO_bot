"""Hydrated profile model.

Value class: the server the profile targets + the player's character
name + all tunables (mobs, manual-control maps, buffs, heal, idle
action, escape, engagement). Transformed into a :class:`HuntConfig` by
``app.session.BotSession``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ro_bot.app.models.server import Server
from ro_bot.hunt.config import (
    AimOffsetSpec,
    BuffSpec,
    DeathReturnConfig,
    EngagementConfig,
    EscapeConfig,
    StaffGuardConfig,
    HealConfig,
    IdleActionConfig,
    OverweightConfig,
    SpSitConfig,
    ReturnToFarmConfig,
)


@dataclass(frozen=True)
class Profile:
    """Complete profile as read from the config file, ready for session wiring."""
    server: Server
    char_name: str
    allowed_mobs: frozenset[str] = field(default_factory=frozenset)
    dangerous_mobs: frozenset[str] = field(default_factory=frozenset)
    manual_control_maps: frozenset[str] = field(default_factory=frozenset)
    aim_offsets: tuple[AimOffsetSpec, ...] = ()
    buffs: tuple[BuffSpec, ...] = ()
    self_buffs: tuple[BuffSpec, ...] = ()
    buff_healer_suppress_sec: float = 0.0
    buff_farm_map_only: bool = True
    buff_step_gap_sec: float = 1.0
    buff_click_self: bool = True
    buff_skill_delay_sec: float = 0.2
    heal: HealConfig | None = None
    death_return: DeathReturnConfig | None = None
    idle_action: IdleActionConfig | None = None
    overweight: OverweightConfig | None = None
    sp_sit: SpSitConfig | None = None
    escape: EscapeConfig | None = None
    staff_guard: StaffGuardConfig | None = None
    engagement: EngagementConfig = field(default_factory=EngagementConfig)
    return_to_farm: ReturnToFarmConfig | None = None
