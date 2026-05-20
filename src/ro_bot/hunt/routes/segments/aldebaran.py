"""Aldebaran save point (``h`` / death) — spawn at Kafra plaza, no walk leg."""

from __future__ import annotations

from ro_bot.hunt.config import FarmRouteWaypoint


class AldebaranPaths:
    HOME_MAP = "aldebaran"
    SAVE_SPAWN: tuple[int, int] = (144, 109)

    @staticmethod
    def from_save_spawn() -> tuple[FarmRouteWaypoint, ...]:
        x, y = AldebaranPaths.SAVE_SPAWN
        return (FarmRouteWaypoint(AldebaranPaths.HOME_MAP, x, y),)
