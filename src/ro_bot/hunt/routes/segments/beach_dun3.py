"""beach_dun3 leg anchor (Comodo warp → exit toward cmd_fild01).

Actual crossing uses :mod:`beach_dun3_transit` (teleport ``t`` into a corridor,
then short ground clicks to x≈287). This module keeps a single spawn waypoint so
the route stays valid for :class:`FarmReturnPlan` and map sync.
"""

from __future__ import annotations

from ro_bot.hunt.config import FarmRouteWaypoint


class BeachDun3Paths:
    @staticmethod
    def from_comodo_warp_to_cmd_fild01() -> tuple[FarmRouteWaypoint, ...]:
        """Typical Comodo-beach warp spawn; transit policy handles the rest."""
        return (FarmRouteWaypoint("beach_dun3", 23, 260),)
