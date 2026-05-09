"""beach_dun3 legs (Comodo warp spawn → exit toward cmd_fild01).

Recorded from sniffer ``Player move`` while map was beach_dun3.
"""

from __future__ import annotations

from ro_bot.hunt.config import FarmRouteWaypoint


class BeachDun3Paths:
    @staticmethod
    def from_comodo_warp_to_cmd_fild01() -> tuple[FarmRouteWaypoint, ...]:
        """0091 after Comodo beach warp → path to cmd_fild01 portal."""
        # Trace 2026-05-09: Map change beach_dun3 (23,260) + Player move until cmd_fild01.
        return (
            FarmRouteWaypoint("beach_dun3", 23, 260),
            FarmRouteWaypoint("beach_dun3", 27, 257),
            FarmRouteWaypoint("beach_dun3", 31, 254),
            FarmRouteWaypoint("beach_dun3", 34, 250),
            FarmRouteWaypoint("beach_dun3", 37, 247),
            FarmRouteWaypoint("beach_dun3", 42, 244),
            FarmRouteWaypoint("beach_dun3", 44, 240),
            FarmRouteWaypoint("beach_dun3", 48, 235),
            FarmRouteWaypoint("beach_dun3", 51, 230),
            FarmRouteWaypoint("beach_dun3", 55, 225),
            FarmRouteWaypoint("beach_dun3", 60, 219),
            FarmRouteWaypoint("beach_dun3", 63, 212),
            FarmRouteWaypoint("beach_dun3", 60, 207),
            FarmRouteWaypoint("beach_dun3", 62, 200),
            FarmRouteWaypoint("beach_dun3", 60, 195),
            FarmRouteWaypoint("beach_dun3", 62, 189),
            FarmRouteWaypoint("beach_dun3", 65, 185),
            FarmRouteWaypoint("beach_dun3", 71, 180),
            FarmRouteWaypoint("beach_dun3", 70, 175),
            FarmRouteWaypoint("beach_dun3", 68, 170),
            FarmRouteWaypoint("beach_dun3", 68, 166),
            FarmRouteWaypoint("beach_dun3", 69, 163),
            FarmRouteWaypoint("beach_dun3", 67, 153),
            FarmRouteWaypoint("beach_dun3", 67, 145),
            FarmRouteWaypoint("beach_dun3", 66, 139),
            FarmRouteWaypoint("beach_dun3", 68, 136),
            FarmRouteWaypoint("beach_dun3", 73, 128),
            FarmRouteWaypoint("beach_dun3", 75, 122),
            FarmRouteWaypoint("beach_dun3", 78, 117),
            FarmRouteWaypoint("beach_dun3", 83, 114),
            FarmRouteWaypoint("beach_dun3", 87, 110),
            FarmRouteWaypoint("beach_dun3", 93, 108),
            FarmRouteWaypoint("beach_dun3", 100, 108),
            FarmRouteWaypoint("beach_dun3", 109, 106),
            FarmRouteWaypoint("beach_dun3", 118, 104),
            FarmRouteWaypoint("beach_dun3", 121, 99),
            FarmRouteWaypoint("beach_dun3", 129, 98),
            FarmRouteWaypoint("beach_dun3", 135, 94),
            FarmRouteWaypoint("beach_dun3", 144, 91),
            FarmRouteWaypoint("beach_dun3", 150, 93),
            FarmRouteWaypoint("beach_dun3", 163, 92),
            FarmRouteWaypoint("beach_dun3", 161, 82),
            FarmRouteWaypoint("beach_dun3", 168, 78),
            FarmRouteWaypoint("beach_dun3", 176, 73),
            FarmRouteWaypoint("beach_dun3", 183, 69),
            FarmRouteWaypoint("beach_dun3", 188, 64),
            FarmRouteWaypoint("beach_dun3", 192, 58),
            FarmRouteWaypoint("beach_dun3", 197, 52),
            FarmRouteWaypoint("beach_dun3", 198, 47),
            FarmRouteWaypoint("beach_dun3", 202, 43),
            FarmRouteWaypoint("beach_dun3", 211, 43),
            FarmRouteWaypoint("beach_dun3", 223, 46),
            FarmRouteWaypoint("beach_dun3", 233, 50),
            FarmRouteWaypoint("beach_dun3", 244, 53),
            FarmRouteWaypoint("beach_dun3", 255, 57),
            FarmRouteWaypoint("beach_dun3", 267, 56),
            FarmRouteWaypoint("beach_dun3", 280, 56),
            FarmRouteWaypoint("beach_dun3", 286, 57),
        )
