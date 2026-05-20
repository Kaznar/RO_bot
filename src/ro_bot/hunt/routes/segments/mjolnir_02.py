"""mjolnir_02 farm leg (Aldebaran Kafra field warp spawn)."""

from __future__ import annotations

from ro_bot.hunt.config import FarmRouteWaypoint


class Mjolnir02Paths:
    FARM_MAP = "mjolnir_02"

    @staticmethod
    def farm_anchor() -> tuple[FarmRouteWaypoint, ...]:
        return (FarmRouteWaypoint("mjolnir_02", 99, 351),)
