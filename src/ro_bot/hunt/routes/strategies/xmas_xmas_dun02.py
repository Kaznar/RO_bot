"""Return plan: xmas resp → walk dungeon → xmas_dun02 farm."""

from __future__ import annotations

from ro_bot.hunt.config import HomePrepStep
from ro_bot.hunt.routes.plan import FarmReturnPlan
from ro_bot.hunt.routes.segments.xmas import XmasPaths
from ro_bot.hunt.routes.segments.xmas_dun01 import XmasDun01Paths
from ro_bot.hunt.routes.segments.xmas_dun02 import XmasDun02Paths
from ro_bot.hunt.routes.strategies.xmas_home_prep import home_prep_xmas


def plan_return_xmas_to_xmas_dun02() -> FarmReturnPlan:
    wps = (
        *XmasPaths.from_resp_to_xmas_dun01(),
        *XmasDun01Paths.from_warp_to_xmas_dun02(),
        *XmasDun02Paths.farm_anchor(),
    )
    return FarmReturnPlan(
        home_map=XmasPaths.HOME_MAP,
        waypoints=wps,
        click_cooldown_sec=0.35,
        arrival_radius_cells=2,
        post_map_change_grace_sec=4.0,
        home_prep=home_prep_xmas(),
        farm_arrival_steps=(
            HomePrepStep(delay_after_sec=3.0),
            HomePrepStep(key="f", delay_after_sec=1.0),
            HomePrepStep(key="c", delay_after_sec=1.0),
        ),
    ).assert_targets_farm(XmasDun02Paths.FARM_MAP)
