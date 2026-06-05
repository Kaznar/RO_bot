"""Map ``active_farm_map`` → Python :class:`FarmReturnPlan`.

Add an entry when you farm a new map; keep segment primitives in
``segments/`` and one composed factory per farm under ``strategies/``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from ro_bot.hunt.config import ReturnToFarmConfig
from ro_bot.hunt.routes.plan import FarmReturnPlan
from ro_bot.hunt.routes.strategies.aldebaran_mjolnir_02 import (
    plan_return_aldebaran_to_mjolnir_02,
)
from ro_bot.hunt.routes.strategies.cmd_fild01 import plan_return_comodo_to_cmd_fild01
from ro_bot.hunt.routes.strategies.pay_fild02 import plan_return_comodo_to_pay_fild02
from ro_bot.hunt.routes.strategies.um_fild03 import plan_return_comodo_to_um_fild03
from ro_bot.hunt.routes.strategies.xmas_xmas_dun02 import (
    plan_return_xmas_to_xmas_dun02,
)
from ro_bot.hunt.routes.strategies.yuno_yuno_fild06 import (
    plan_return_yuno_to_yuno_fild06,
)

FarmReturnPlanFactory = Callable[[], FarmReturnPlan]

logger = logging.getLogger("ro_bot.hunt")

#: Registry keyed by ``ReturnToFarmConfig.active_farm_map`` string.
FARM_RETURN_PLAN_FACTORIES: dict[str, FarmReturnPlanFactory] = {
    "cmd_fild01": plan_return_comodo_to_cmd_fild01,
    "mjolnir_02": plan_return_aldebaran_to_mjolnir_02,
    "pay_fild02": plan_return_comodo_to_pay_fild02,
    "um_fild03": plan_return_comodo_to_um_fild03,
    "xmas_dun02": plan_return_xmas_to_xmas_dun02,
    "yuno_fild06": plan_return_yuno_to_yuno_fild06,
}


def resolve_farm_return_plan(active_farm_map: str | None) -> FarmReturnPlan | None:
    """Return a plan for ``active_farm_map``, or ``None`` if unregistered."""
    if active_farm_map is None:
        return None
    key = active_farm_map.strip()
    if not key:
        return None
    factory = FARM_RETURN_PLAN_FACTORIES.get(key)
    if factory is None:
        return None
    return factory()


def augment_return_to_farm_from_registry(
    rtf: ReturnToFarmConfig | None,
) -> ReturnToFarmConfig | None:
    """Merge registry plans or config skill-warp restock into ``ReturnToFarmConfig``."""
    if rtf is None:
        return None
    from dataclasses import replace

    from ro_bot.hunt.routes.skill_warp_restock import (
        ensure_home_route_for_skill_warp,
        has_skill_warp_restock,
    )

    if not rtf.home_navigation_enabled:
        rtf = replace(rtf, home_route=None, farm_arrival_steps=())
    if has_skill_warp_restock(rtf):
        rtf = ensure_home_route_for_skill_warp(rtf)
        if rtf.home_route is not None:
            return rtf
    if rtf.home_route is not None:
        return rtf
    plan = resolve_farm_return_plan(rtf.active_farm_map)
    if plan is None:
        farm = (rtf.active_farm_map or "").strip()
        if farm:
            known = ", ".join(sorted(FARM_RETURN_PLAN_FACTORIES))
            logger.warning(
                "No farm return plan for active_farm_map=%r — "
                "home_prep/home_route disabled (known: %s)",
                farm, known,
            )
        return rtf
    merged_prep = rtf.home_prep if rtf.home_prep is not None else plan.home_prep
    merged_arrival = (
        rtf.farm_arrival_steps
        if rtf.farm_arrival_steps
        else plan.farm_arrival_steps
    )
    return replace(
        rtf,
        home_route=plan.as_home_route_config(),
        home_prep=merged_prep,
        farm_arrival_steps=merged_arrival,
    )
