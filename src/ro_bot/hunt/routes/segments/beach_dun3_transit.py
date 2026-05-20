"""beach_dun3 return leg: random teleport (`t`) until a corridor, then short walks.

Corridor (inclusive): x 216–284, y 30–68. Map exit column x≈286, y 56–58.
Used by :class:`FarmHomeRoutePolicy` instead of a long fixed waypoint chain.
"""
from __future__ import annotations

from typing import Protocol


class _HasMapName(Protocol):
    map_name: str


def teleport_key() -> str:
    """Skill / item bound to the same key as ``profile.idle_action.key`` (e.g. wing)."""
    return "t"


def teleport_cooldown_sec() -> float:
    """Min interval between ``t`` presses while hunting a random landing."""
    return 0.4


def corridor_bounds() -> tuple[int, int, int, int]:
    """``(xmin, ymin, xmax, ymax)`` inclusive."""
    return (216, 30, 284, 68)


def exit_column_x() -> int:
    """East warp column (cells)."""
    return 286


def exit_y_min_max() -> tuple[int, int]:
    """Inclusive Y band at the warp (56, 57, 58)."""
    return (56, 58)


def exit_cell() -> tuple[int, int]:
    """Preferred ground click at the warp (mid Y)."""
    ymin, ymax = exit_y_min_max()
    return (exit_column_x(), (ymin + ymax) // 2)


def in_corridor(x: int, y: int) -> bool:
    xmin, ymin, xmax, ymax = corridor_bounds()
    return xmin <= x <= xmax and ymin <= y <= ymax


def at_exit_zone(x: int, y: int, *, x_slack: int = 2) -> bool:
    """Near the warp tile: column ``286`` and y in 56..58."""
    ymin, ymax = exit_y_min_max()
    ex = exit_column_x()
    return abs(x - ex) <= x_slack and ymin <= y <= ymax


def _clamp_exit_y(py: int) -> int:
    ymin, ymax = exit_y_min_max()
    return max(ymin, min(ymax, py))


def _clamp_y(py: int) -> int:
    _, ymin, _, ymax = corridor_bounds()
    margin = 2
    return max(ymin + margin, min(ymax - margin, py))


def next_walk_cell(px: int, py: int) -> tuple[int, int]:
    """4–5 cell steps: bias east; nudge toward exit column x=286, y in 56..58."""
    xmin, ymin, xmax, ymax = corridor_bounds()
    ex = exit_column_x()
    ey = _clamp_exit_y(py)
    stride = 5

    if at_exit_zone(px, py):
        return (ex, ey)

    # Still inside corridor but not at exit yet
    if px < 248:
        nx = min(px + stride, 248)
        return (nx, _clamp_y(py))

    if px < ex - 2:
        nx = min(px + stride, ex)
        ny = py + max(-stride, min(stride, ey - py))
        return (nx, max(ymin + 1, min(ymax - 1, ny)))

    return (ex, max(ymin + 1, min(ymax - 1, _clamp_exit_y(py))))


def is_wing_reposition_on_map(from_map: str | None, to_map: str) -> bool:
    """True when a skill teleport re-lands on the same map (0091 same→same)."""
    return from_map is not None and from_map == to_map == "beach_dun3"


def first_waypoint_index_after_map(
    waypoints: tuple[_HasMapName, ...],
    start_idx: int,
    map_name: str,
) -> int | None:
    """First index ``>= start_idx`` whose map is not ``map_name``, or ``None``."""
    for j in range(start_idx, len(waypoints)):
        if waypoints[j].map_name != map_name:
            return j
    return None
