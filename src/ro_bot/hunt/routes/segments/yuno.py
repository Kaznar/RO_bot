"""Yuno town leg — resp / save ``h`` landing → north exit to yuno_fild04."""

from __future__ import annotations

from ro_bot.hunt.config import FarmRouteWaypoint


class YunoPaths:
    HOME_MAP = "yuno"
    #: Typical resp / save spawn after ``h`` (sniffer 2026-05-20).
    SAVE_SPAWN: tuple[int, int] = (157, 177)

    @staticmethod
    def from_resp_to_yuno_fild04() -> tuple[FarmRouteWaypoint, ...]:
        """Every ``Player move`` on yuno before 0091 → yuno_fild04 (2026-05-20)."""
        return (
            FarmRouteWaypoint("yuno", 157, 177),
            FarmRouteWaypoint("yuno", 157, 170),
            FarmRouteWaypoint("yuno", 157, 163),
            FarmRouteWaypoint("yuno", 157, 156),
            FarmRouteWaypoint("yuno", 157, 149),
            FarmRouteWaypoint("yuno", 157, 142),
            FarmRouteWaypoint("yuno", 157, 135),
            FarmRouteWaypoint("yuno", 157, 128),
            FarmRouteWaypoint("yuno", 157, 121),
            FarmRouteWaypoint("yuno", 157, 114),
            FarmRouteWaypoint("yuno", 170, 114),
            FarmRouteWaypoint("yuno", 170, 106),
            FarmRouteWaypoint("yuno", 170, 98),
            FarmRouteWaypoint("yuno", 170, 90),
            FarmRouteWaypoint("yuno", 161, 83),
            FarmRouteWaypoint("yuno", 158, 76),
            FarmRouteWaypoint("yuno", 158, 67),
            FarmRouteWaypoint("yuno", 158, 59),
            FarmRouteWaypoint("yuno", 158, 52),
            FarmRouteWaypoint("yuno", 158, 45),
            FarmRouteWaypoint("yuno", 158, 38),
            FarmRouteWaypoint("yuno", 158, 31),
            FarmRouteWaypoint("yuno", 158, 24),
            FarmRouteWaypoint("yuno", 158, 20),
            FarmRouteWaypoint("yuno", 158, 14),
        )
