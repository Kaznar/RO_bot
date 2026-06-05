"""pay_fild02 — anchors after Comodo Open Warp (skill ``x``)."""

from __future__ import annotations

from ro_bot.hunt.config import FarmRouteWaypoint


class PayFild02Paths:
    @staticmethod
    def after_comodo_skill_warp() -> tuple[FarmRouteWaypoint, ...]:
        """Typical landing + farm spot (tune from sniffer / PREP_SNAPSHOT)."""
        return (
            FarmRouteWaypoint("pay_fild02", 234, 136),
            FarmRouteWaypoint("pay_fild02", 236, 120),
        )
