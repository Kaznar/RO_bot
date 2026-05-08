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
    EngagementConfig,
    EscapeConfig,
    HealConfig,
    IdleActionConfig,
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
    heal: HealConfig | None = None
    idle_action: IdleActionConfig | None = None
    escape: EscapeConfig | None = None
    engagement: EngagementConfig = field(default_factory=EngagementConfig)
    return_to_farm: ReturnToFarmConfig | None = None
