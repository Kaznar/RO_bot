"""yuno_fild03 leg — west warp-in → south-west exit to yuno_fild06."""

from __future__ import annotations

from ro_bot.hunt.config import FarmRouteWaypoint


class YunoFild03Paths:
    @staticmethod
    def from_yuno_fild04_warp_to_yuno_fild06() -> tuple[FarmRouteWaypoint, ...]:
        """Every ``Player move`` on yuno_fild03 before 0091 → yuno_fild06."""
        return (
            FarmRouteWaypoint("yuno_fild03", 22, 155),
            FarmRouteWaypoint("yuno_fild03", 29, 161),
            FarmRouteWaypoint("yuno_fild03", 37, 167),
            FarmRouteWaypoint("yuno_fild03", 48, 171),
            FarmRouteWaypoint("yuno_fild03", 56, 174),
            FarmRouteWaypoint("yuno_fild03", 63, 179),
            FarmRouteWaypoint("yuno_fild03", 69, 185),
            FarmRouteWaypoint("yuno_fild03", 75, 191),
            FarmRouteWaypoint("yuno_fild03", 83, 193),
            FarmRouteWaypoint("yuno_fild03", 93, 195),
            FarmRouteWaypoint("yuno_fild03", 101, 201),
            FarmRouteWaypoint("yuno_fild03", 108, 206),
            FarmRouteWaypoint("yuno_fild03", 113, 212),
            FarmRouteWaypoint("yuno_fild03", 118, 219),
            FarmRouteWaypoint("yuno_fild03", 122, 226),
            FarmRouteWaypoint("yuno_fild03", 125, 233),
            FarmRouteWaypoint("yuno_fild03", 130, 240),
            FarmRouteWaypoint("yuno_fild03", 136, 246),
            FarmRouteWaypoint("yuno_fild03", 143, 252),
            FarmRouteWaypoint("yuno_fild03", 149, 258),
            FarmRouteWaypoint("yuno_fild03", 152, 265),
            FarmRouteWaypoint("yuno_fild03", 155, 273),
            FarmRouteWaypoint("yuno_fild03", 157, 282),
            FarmRouteWaypoint("yuno_fild03", 160, 290),
            FarmRouteWaypoint("yuno_fild03", 168, 299),
            FarmRouteWaypoint("yuno_fild03", 178, 305),
            FarmRouteWaypoint("yuno_fild03", 188, 310),
            FarmRouteWaypoint("yuno_fild03", 196, 316),
            FarmRouteWaypoint("yuno_fild03", 198, 325),
            FarmRouteWaypoint("yuno_fild03", 202, 334),
            FarmRouteWaypoint("yuno_fild03", 208, 342),
            FarmRouteWaypoint("yuno_fild03", 213, 351),
            FarmRouteWaypoint("yuno_fild03", 218, 360),
            FarmRouteWaypoint("yuno_fild03", 222, 369),
            FarmRouteWaypoint("yuno_fild03", 220, 376),
            FarmRouteWaypoint("yuno_fild03", 214, 383),
        )
