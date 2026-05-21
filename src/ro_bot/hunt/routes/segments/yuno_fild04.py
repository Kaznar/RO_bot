"""yuno_fild04 leg — north gate warp-in → east exit to yuno_fild03."""

from __future__ import annotations

from ro_bot.hunt.config import FarmRouteWaypoint


class YunoFild04Paths:
    @staticmethod
    def from_yuno_warp_to_yuno_fild03() -> tuple[FarmRouteWaypoint, ...]:
        """Every ``Player move`` on yuno_fild04 before 0091 → yuno_fild03."""
        return (
            FarmRouteWaypoint("yuno_fild04", 231, 284),
            FarmRouteWaypoint("yuno_fild04", 231, 279),
            FarmRouteWaypoint("yuno_fild04", 231, 274),
            FarmRouteWaypoint("yuno_fild04", 231, 269),
            FarmRouteWaypoint("yuno_fild04", 231, 264),
            FarmRouteWaypoint("yuno_fild04", 231, 258),
            FarmRouteWaypoint("yuno_fild04", 231, 252),
            FarmRouteWaypoint("yuno_fild04", 231, 246),
            FarmRouteWaypoint("yuno_fild04", 231, 240),
            FarmRouteWaypoint("yuno_fild04", 231, 234),
            FarmRouteWaypoint("yuno_fild04", 231, 228),
            FarmRouteWaypoint("yuno_fild04", 231, 219),
            FarmRouteWaypoint("yuno_fild04", 231, 211),
            FarmRouteWaypoint("yuno_fild04", 231, 203),
            FarmRouteWaypoint("yuno_fild04", 232, 198),
            FarmRouteWaypoint("yuno_fild04", 241, 195),
            FarmRouteWaypoint("yuno_fild04", 241, 188),
            FarmRouteWaypoint("yuno_fild04", 241, 182),
            FarmRouteWaypoint("yuno_fild04", 241, 176),
            FarmRouteWaypoint("yuno_fild04", 241, 170),
            FarmRouteWaypoint("yuno_fild04", 241, 164),
            FarmRouteWaypoint("yuno_fild04", 241, 158),
            FarmRouteWaypoint("yuno_fild04", 241, 152),
            FarmRouteWaypoint("yuno_fild04", 241, 145),
            FarmRouteWaypoint("yuno_fild04", 241, 138),
            FarmRouteWaypoint("yuno_fild04", 246, 131),
            FarmRouteWaypoint("yuno_fild04", 254, 126),
            FarmRouteWaypoint("yuno_fild04", 264, 122),
            FarmRouteWaypoint("yuno_fild04", 274, 117),
            FarmRouteWaypoint("yuno_fild04", 284, 113),
            FarmRouteWaypoint("yuno_fild04", 293, 107),
            FarmRouteWaypoint("yuno_fild04", 303, 106),
            FarmRouteWaypoint("yuno_fild04", 313, 107),
            FarmRouteWaypoint("yuno_fild04", 319, 112),
            FarmRouteWaypoint("yuno_fild04", 327, 117),
            FarmRouteWaypoint("yuno_fild04", 333, 122),
            FarmRouteWaypoint("yuno_fild04", 338, 130),
            FarmRouteWaypoint("yuno_fild04", 345, 137),
            FarmRouteWaypoint("yuno_fild04", 356, 141),
            FarmRouteWaypoint("yuno_fild04", 367, 143),
            FarmRouteWaypoint("yuno_fild04", 375, 150),
        )
