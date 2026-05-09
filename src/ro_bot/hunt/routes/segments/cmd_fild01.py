"""cmd_fild01 leg (beach_dun3 warp-in → um_fild03 warp).

Recorded from sniffer ``Player move`` while map was cmd_fild01.
"""

from __future__ import annotations

from ro_bot.hunt.config import FarmRouteWaypoint


class CmdFild01Paths:
    @staticmethod
    def from_beach_dun3_warp_to_um_fild03() -> tuple[FarmRouteWaypoint, ...]:
        """0091 spawn on cmd_fild01 → approach warp to um_fild03."""
        return (
            FarmRouteWaypoint("cmd_fild01", 30, 317),
            FarmRouteWaypoint("cmd_fild01", 36, 318),
            FarmRouteWaypoint("cmd_fild01", 40, 322),
            FarmRouteWaypoint("cmd_fild01", 44, 326),
            FarmRouteWaypoint("cmd_fild01", 49, 330),
            FarmRouteWaypoint("cmd_fild01", 54, 335),
            FarmRouteWaypoint("cmd_fild01", 59, 340),
            FarmRouteWaypoint("cmd_fild01", 64, 344),
            FarmRouteWaypoint("cmd_fild01", 69, 348),
            FarmRouteWaypoint("cmd_fild01", 71, 353),
            FarmRouteWaypoint("cmd_fild01", 72, 359),
            FarmRouteWaypoint("cmd_fild01", 75, 361),
            FarmRouteWaypoint("cmd_fild01", 77, 366),
        )
