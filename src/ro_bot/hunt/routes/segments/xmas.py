"""xmas town leg — save ``h`` landing → dungeon entrance (xmas_dun01)."""

from __future__ import annotations

from ro_bot.hunt.config import FarmRouteWaypoint


class XmasPaths:
    HOME_MAP = "xmas"
    #: Typical resp / save spawn after ``h`` (sniffer 2026-06-03).
    SAVE_SPAWN: tuple[int, int] = (148, 129)

    @staticmethod
    def from_resp_to_xmas_dun01() -> tuple[FarmRouteWaypoint, ...]:
        """Every ``Player move`` on xmas before 0091 → xmas_dun01 (2026-06-03)."""
        return (
            FarmRouteWaypoint("xmas", 148, 129),
            FarmRouteWaypoint("xmas", 140, 131),
            FarmRouteWaypoint("xmas", 137, 139),
            FarmRouteWaypoint("xmas", 136, 147),
            FarmRouteWaypoint("xmas", 138, 156),
            FarmRouteWaypoint("xmas", 141, 166),
            FarmRouteWaypoint("xmas", 144, 175),
            FarmRouteWaypoint("xmas", 146, 182),
            FarmRouteWaypoint("xmas", 147, 189),
            FarmRouteWaypoint("xmas", 147, 195),
            FarmRouteWaypoint("xmas", 147, 202),
            FarmRouteWaypoint("xmas", 147, 210),
            FarmRouteWaypoint("xmas", 145, 217),
            FarmRouteWaypoint("xmas", 143, 225),
            FarmRouteWaypoint("xmas", 133, 228),
            FarmRouteWaypoint("xmas", 126, 234),
            FarmRouteWaypoint("xmas", 124, 242),
            FarmRouteWaypoint("xmas", 123, 251),
            FarmRouteWaypoint("xmas", 129, 258),
            FarmRouteWaypoint("xmas", 134, 266),
            FarmRouteWaypoint("xmas", 140, 273),
            FarmRouteWaypoint("xmas", 144, 281),
            FarmRouteWaypoint("xmas", 144, 290),
            FarmRouteWaypoint("xmas", 144, 297),
            FarmRouteWaypoint("xmas", 144, 306),
            FarmRouteWaypoint("xmas", 144, 311),
            FarmRouteWaypoint("xmas", 143, 314),
        )
