"""Map cell ↔ screen pixel projection.

The RO classic client uses a player-centered camera tilted ~30°.
As a first-pass approximation we treat the projection as linear with
independent per-axis scale::

    dx_cells = mob_x - player_x
    dy_cells = mob_y - player_y                 # Y grows northward in RO

    target_px_x = left + width/2 + dx * px_per_cell_x
    target_px_y = top  + height/2 - dy * px_per_cell_y

The ``CameraProjection`` dataclass bundles the per-server scale and
camera offsets (where the player sprite sits relative to the
geometric center of the client area).
"""

from __future__ import annotations

from dataclasses import dataclass

from ro_bot.core.window import WindowRect


@dataclass(frozen=True)
class CameraProjection:
    """Per-server projection constants.

    Supplied by the app layer (loaded from the JSON config). Swapping
    server or client resolution is a config-only change — this class
    stays immutable at runtime.
    """
    px_per_cell_x: float
    px_per_cell_y: float
    camera_offset_x: float = 0.0
    camera_offset_y: float = 0.0

    def map_to_screen(
        self,
        player_cell: tuple[int, int],
        mob_cell: tuple[float, float],
        rect: WindowRect,
    ) -> tuple[int, int]:
        """Return absolute screen pixel for ``mob_cell`` under this projection."""
        px, py = player_cell
        mx, my = mob_cell
        cx = rect.left + rect.width / 2.0 + self.camera_offset_x
        cy = rect.top + rect.height / 2.0 + self.camera_offset_y
        sx = cx + (mx - px) * self.px_per_cell_x
        sy = cy - (my - py) * self.px_per_cell_y
        return int(round(sx)), int(round(sy))


def clamp_to_rect(
    point: tuple[int, int], rect: WindowRect,
) -> tuple[int, int]:
    """Clamp ``point`` into ``rect`` so HID moves can't steer the
    cursor across monitors or outside the game window.
    """
    x, y = point
    x = max(rect.left, min(rect.left + rect.width - 1, x))
    y = max(rect.top, min(rect.top + rect.height - 1, y))
    return x, y
