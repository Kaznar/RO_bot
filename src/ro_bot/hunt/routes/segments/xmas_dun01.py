"""xmas_dun01 leg — warp-in → south-west exit to xmas_dun02."""

from __future__ import annotations

from ro_bot.hunt.config import FarmRouteWaypoint


class XmasDun01Paths:
    @staticmethod
    def from_warp_to_xmas_dun02() -> tuple[FarmRouteWaypoint, ...]:
        """Every ``Player move`` on xmas_dun01 before 0091 → xmas_dun02 (2026-06-03)."""
        return (
            FarmRouteWaypoint("xmas_dun01", 205, 16),
            FarmRouteWaypoint("xmas_dun01", 204, 26),
            FarmRouteWaypoint("xmas_dun01", 203, 36),
            FarmRouteWaypoint("xmas_dun01", 202, 46),
            FarmRouteWaypoint("xmas_dun01", 198, 55),
            FarmRouteWaypoint("xmas_dun01", 194, 64),
            FarmRouteWaypoint("xmas_dun01", 186, 69),
            FarmRouteWaypoint("xmas_dun01", 186, 79),
            FarmRouteWaypoint("xmas_dun01", 186, 88),
            FarmRouteWaypoint("xmas_dun01", 178, 96),
            FarmRouteWaypoint("xmas_dun01", 173, 105),
            FarmRouteWaypoint("xmas_dun01", 167, 114),
            FarmRouteWaypoint("xmas_dun01", 167, 123),
            FarmRouteWaypoint("xmas_dun01", 167, 131),
            FarmRouteWaypoint("xmas_dun01", 157, 131),
            FarmRouteWaypoint("xmas_dun01", 147, 134),
            FarmRouteWaypoint("xmas_dun01", 143, 141),
            FarmRouteWaypoint("xmas_dun01", 137, 139),
            FarmRouteWaypoint("xmas_dun01", 132, 134),
            FarmRouteWaypoint("xmas_dun01", 129, 130),
        )
