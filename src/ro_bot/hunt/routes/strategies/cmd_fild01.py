"""Registered strategy for ``active_farm_map == cmd_fild01``."""

from __future__ import annotations

from ro_bot.hunt.routes.plan import FarmReturnPlan
from ro_bot.hunt.routes.strategies.comodo_home_prep import home_prep_comodo
from ro_bot.hunt.routes.segments.beach_dun3 import BeachDun3Paths
from ro_bot.hunt.routes.segments.cmd_fild01 import CmdFild01Paths
def plan_return_comodo_to_cmd_fild01() -> FarmReturnPlan:
    """Comodo ``home_prep`` (skill warp ``x``) → beach_dun3 → cmd_fild01."""
    wps = (
        *BeachDun3Paths.from_comodo_warp_to_cmd_fild01(),
        *CmdFild01Paths.cmd_fild01_farm_anchor(),
    )
    return FarmReturnPlan(
        home_map=ComodoPaths.HOME_MAP,
        waypoints=wps,
        click_cooldown_sec=0.0,
        arrival_radius_cells=2,
        home_prep=home_prep_comodo(),
    ).assert_targets_farm("cmd_fild01")
