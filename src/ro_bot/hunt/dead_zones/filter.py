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

    def contains_screen_px(self, screen_x: int, screen_y: int) -> bool:
        """True if absolute screen pixel is inside any configured zone."""
        if not self.zones:
            return False
        return any(
            z.contains_screen_px(screen_x, screen_y, self.rect)
            for z in self.zones
        )

    def contains_client_px(self, client_x: int, client_y: int) -> bool:
        """True if client-relative pixel is inside any configured zone."""
        return self.contains_screen_px(
            self.rect.left + client_x,
            self.rect.top + client_y,
        )

    def segment_intersects(
        self,
        p0: tuple[int, int],
        p1: tuple[int, int],
        *,
        samples: int = 16,
    ) -> bool:
        """True if any sample along the screen segment lies in a dead zone."""
        if not self.zones:
            return False
        n = max(1, samples)
        for i in range(n + 1):
            t = i / n
            x = int(p0[0] + (p1[0] - p0[0]) * t)
            y = int(p0[1] + (p1[1] - p0[1]) * t)
            if self.contains_screen_px(x, y):
                return True
        return False

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
        return self.contains_screen_px(clamped[0], clamped[1])
