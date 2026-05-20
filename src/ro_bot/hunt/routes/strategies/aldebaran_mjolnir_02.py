"""Return plan: Aldebaran save → prep → Kafra warp → mjolnir_02 farm."""

from __future__ import annotations

from ro_bot.hunt.routes.plan import FarmReturnPlan
from ro_bot.hunt.routes.segments.aldebaran import AldebaranPaths
from ro_bot.hunt.routes.segments.mjolnir_02 import Mjolnir02Paths
from ro_bot.hunt.routes.strategies.aldebaran_home_prep import home_prep_aldebaran


def plan_return_aldebaran_to_mjolnir_02() -> FarmReturnPlan:
    wps = (
        *AldebaranPaths.from_save_spawn(),
        *Mjolnir02Paths.farm_anchor(),
    )
    return FarmReturnPlan(
        home_map=AldebaranPaths.HOME_MAP,
        waypoints=wps,
        click_cooldown_sec=0.0,
        arrival_radius_cells=2,
        home_prep=home_prep_aldebaran(),
    ).assert_targets_farm(Mjolnir02Paths.FARM_MAP)
