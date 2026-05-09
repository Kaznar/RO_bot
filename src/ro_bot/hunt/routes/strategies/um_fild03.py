"""Registered strategy for ``active_farm_map == um_fild03``.

Edit segment imports / ordering here; add sibling modules for other farms.
"""

from __future__ import annotations

from ro_bot.hunt.routes.plan import FarmReturnPlan
from ro_bot.hunt.routes.strategies.comodo_home_prep import home_prep_comodo
from ro_bot.hunt.routes.segments.beach_dun3 import BeachDun3Paths
from ro_bot.hunt.routes.segments.cmd_fild01 import CmdFild01Paths
from ro_bot.hunt.routes.segments.comodo import ComodoPaths
from ro_bot.hunt.routes.segments.um_fild import UmFildPaths


def plan_return_comodo_to_um_fild03() -> FarmReturnPlan:
    """Comodo (after ``h``) → beach_dun3 → cmd_fild01 → um_fild03."""
    wps = (
        *ComodoPaths.from_resp_after_h_to_beach_dun3(),
        *BeachDun3Paths.from_comodo_warp_to_cmd_fild01(),
        *CmdFild01Paths.from_beach_dun3_warp_to_um_fild03(),
        *UmFildPaths.um_fild03_farm_anchor(),
    )
    return FarmReturnPlan(
        home_map=ComodoPaths.HOME_MAP,
        waypoints=wps,
        click_cooldown_sec=0.0,
        arrival_radius_cells=2,
        home_prep=home_prep_comodo(),
    ).assert_targets_farm("um_fild03")
