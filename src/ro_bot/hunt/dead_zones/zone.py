"""Rectangular dead-zone glued to a window corner.

Dead zones are screen regions the bot must never click (UI overlays,
HUD panels). They're anchored to a window corner with (inset_x,
inset_y, width, height) — so resizing the game window keeps them
attached to the right HUD element, since RO panels have fixed pixel
sizes regardless of resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ro_bot.core.window import WindowRect

Anchor = Literal["TL", "TR", "BL", "BR"]


@dataclass(frozen=True)
class DeadZone:
    """Rectangle anchored to ``anchor`` corner of the window.

    ``inset_x`` / ``inset_y`` are distances from the named corner
    *inward* to the rectangle's near edges. Example::

        DeadZone("TR", 0, 0, 460, 80)

    glues the zone's top-right corner to the window's top-right corner
    and extends 460 px left × 80 px down.
    """
    anchor: Anchor
    inset_x: int
    inset_y: int
    width: int
    height: int

    def absolute_origin(self, rect: WindowRect) -> tuple[int, int]:
        """Top-left corner of the zone in absolute screen coordinates.

        Collapses all four anchors onto one top-left point so callers
        can reuse the same rectangle math regardless of anchor.
        """
        if self.anchor == "TL":
            x0 = rect.left + self.inset_x
            y0 = rect.top + self.inset_y
        elif self.anchor == "TR":
            x0 = rect.left + rect.width - self.inset_x - self.width
            y0 = rect.top + self.inset_y
        elif self.anchor == "BL":
            x0 = rect.left + self.inset_x
            y0 = rect.top + rect.height - self.inset_y - self.height
        else:  # BR
            x0 = rect.left + rect.width - self.inset_x - self.width
            y0 = rect.top + rect.height - self.inset_y - self.height
        return x0, y0

    def contains_screen_px(self, px: int, py: int, rect: WindowRect) -> bool:
        """True if absolute screen pixel (px, py) is inside this zone."""
        x0, y0 = self.absolute_origin(rect)
        return x0 <= px < x0 + self.width and y0 <= py < y0 + self.height
