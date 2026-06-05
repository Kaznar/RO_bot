"""xmas_dun02 farm leg (xmas_dun01 exit warp spawn)."""

from __future__ import annotations

from ro_bot.hunt.config import FarmRouteWaypoint


class XmasDun02Paths:
    FARM_MAP = "xmas_dun02"

    @staticmethod
    def farm_anchor() -> tuple[FarmRouteWaypoint, ...]:
        return (FarmRouteWaypoint("xmas_dun02", 131, 130),)
