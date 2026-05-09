"""Reusable Comodo cell paths (compose into larger strategies).

Each method returns waypoints on ``comodo`` only — field legs live in
other segment modules or strategy files.
"""

from __future__ import annotations

from ro_bot.hunt.config import FarmRouteWaypoint


class ComodoPaths:
    """Named legs starting from town / storage-adjacent cells."""

    HOME_MAP = "comodo"

    @staticmethod
    def from_resp_after_h_to_beach_dun3() -> tuple[FarmRouteWaypoint, ...]:
        """Storage ``h`` landing → beach_dun3 warp (sniffer ``Player move`` trail)."""
        return (
            FarmRouteWaypoint("comodo", 222, 156),
            FarmRouteWaypoint("comodo", 236, 158),
            FarmRouteWaypoint("comodo", 250, 167),
            FarmRouteWaypoint("comodo", 262, 173),
            FarmRouteWaypoint("comodo", 276, 173),
            FarmRouteWaypoint("comodo", 290, 173),
            FarmRouteWaypoint("comodo", 302, 178),
            FarmRouteWaypoint("comodo", 314, 181),
            FarmRouteWaypoint("comodo", 323, 176),
            FarmRouteWaypoint("comodo", 333, 175),
        )

   