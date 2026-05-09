"""Umbala field legs (replace coords with your spawn / farm anchor)."""

from __future__ import annotations

from ro_bot.hunt.config import FarmRouteWaypoint


class UmFildPaths:
    @staticmethod
    def um_fild03_farm_anchor() -> tuple[FarmRouteWaypoint, ...]:
        """Spawn cell after cmd_fild01 → um_fild03 warp (sniffer 0091)."""
        return (FarmRouteWaypoint("um_fild03", 114, 53),)
