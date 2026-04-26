"""Hydrated profile model.

Value class: the server the profile targets + the player's character
name + all tunables (mobs, maps, buffs, heal, idle action, escape,
engagement). Transformed into a :class:`HuntConfig` by
``app.session.BotSession``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ro_bot.app.models.server import Server
from ro_bot.hunt.config import (
    BuffSpec,
    EngagementConfig,
    EscapeConfig,
    HealConfig,
    IdleActionConfig,
)


@dataclass(frozen=True)
class Profile:
    """Complete profile as read from SQLite, ready for session wiring."""
    id: int
    name: str
    server: Server
    char_name: str
    primary_map: str = ""
    allowed_mobs: frozenset[str] = field(default_factory=frozenset)
    dangerous_mobs: frozenset[str] = field(default_factory=frozenset)
    maps: frozenset[str] = field(default_factory=frozenset)
    buffs: tuple[BuffSpec, ...] = ()
    heal: HealConfig | None = None
    idle_action: IdleActionConfig | None = None
    escape: EscapeConfig | None = None
    engagement: EngagementConfig = field(default_factory=EngagementConfig)
