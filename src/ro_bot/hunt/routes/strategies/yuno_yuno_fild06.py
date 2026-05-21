"""Return plan: Yuno resp → walk fields → yuno_fild06 farm."""

from __future__ import annotations

from ro_bot.hunt.config import HomePrepStep
from ro_bot.hunt.routes.plan import FarmReturnPlan
from ro_bot.hunt.routes.segments.yuno import YunoPaths
from ro_bot.hunt.routes.segments.yuno_fild03 import YunoFild03Paths
from ro_bot.hunt.routes.segments.yuno_fild04 import YunoFild04Paths
from ro_bot.hunt.routes.segments.yuno_fild06 import YunoFild06Paths
from ro_bot.hunt.routes.strategies.yuno_home_prep import home_prep_yuno


def plan_return_yuno_to_yuno_fild06() -> FarmReturnPlan:
    wps = (
        *YunoPaths.from_resp_to_yuno_fild04(),
        *YunoFild04Paths.from_yuno_warp_to_yuno_fild03(),
        *YunoFild03Paths.from_yuno_fild04_warp_to_yuno_fild06(),
        *YunoFild06Paths.farm_anchor(),
    )
    return FarmReturnPlan(
        home_map=YunoPaths.HOME_MAP,
        waypoints=wps,
        click_cooldown_sec=0.35,
        arrival_radius_cells=2,
        post_map_change_grace_sec=4.0,
        home_prep=home_prep_yuno(),
        farm_arrival_steps=(
            HomePrepStep(delay_after_sec=3.0),
            HomePrepStep(key="f", delay_after_sec=1.0),
            HomePrepStep(key="c", delay_after_sec=1.0),
        ),
    ).assert_targets_farm(YunoFild06Paths.FARM_MAP)
