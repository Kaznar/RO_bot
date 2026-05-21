"""yuno_fild06 farm leg (yuno_fild03 south exit warp spawn)."""

from __future__ import annotations

from ro_bot.hunt.config import FarmRouteWaypoint


class YunoFild06Paths:
    FARM_MAP = "yuno_fild06"

    @staticmethod
    def farm_anchor() -> tuple[FarmRouteWaypoint, ...]:
        return (FarmRouteWaypoint("yuno_fild06", 217, 29),)
