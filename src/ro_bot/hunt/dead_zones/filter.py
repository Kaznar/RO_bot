"""Dead-zone containment test for a mob cell.

Given a player position, a mob cell, the current camera projection,
and a set of zones, determine whether clicking that mob would land on
a HUD panel.
"""

from __future__ import annotations

from dataclasses import dataclass

from ro_bot.core.projection.camera import CameraProjection, clamp_to_rect
from ro_bot.core.window import WindowRect
from ro_bot.hunt.dead_zones.zone import DeadZone


@dataclass(frozen=True)
class DeadZoneFilter:
    """Stateless predicate: does a map cell project onto the HUD?"""
    zones: tuple[DeadZone, ...]
    projection: CameraProjection
    rect: WindowRect

    def contains(
        self,
        player_cell: tuple[int, int],
        mob_cell: tuple[int, int],
    ) -> bool:
        """True if `mob_cell` projects inside any of this filter's zones."""
        if not self.zones:
            return False
        target_px = self.projection.map_to_screen(
            player_cell, mob_cell, self.rect,
        )
        clamped = clamp_to_rect(target_px, self.rect)
        return any(
            z.contains_screen_px(clamped[0], clamped[1], self.rect)
            for z in self.zones
        )
