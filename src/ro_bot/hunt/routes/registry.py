"""Map ``active_farm_map`` → Python :class:`FarmReturnPlan`.

Add an entry when you farm a new map; keep segment primitives in
``segments/`` and one composed factory per farm under ``strategies/``.
"""

from __future__ import annotations

from collections.abc import Callable

from ro_bot.hunt.config import ReturnToFarmConfig
from ro_bot.hunt.routes.plan import FarmReturnPlan
from ro_bot.hunt.routes.strategies.cmd_fild01 import plan_return_comodo_to_cmd_fild01
from ro_bot.hunt.routes.strategies.um_fild03 import plan_return_comodo_to_um_fild03

FarmReturnPlanFactory = Callable[[], FarmReturnPlan]

#: Registry keyed by ``ReturnToFarmConfig.active_farm_map`` string.
FARM_RETURN_PLAN_FACTORIES: dict[str, FarmReturnPlanFactory] = {
    "cmd_fild01": plan_return_comodo_to_cmd_fild01,
    "um_fild03": plan_return_comodo_to_um_fild03,
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
    """Attach registry ``home_route`` unless JSON already set or nav disabled."""
    if rtf is None:
        return None
    from dataclasses import replace

    if not rtf.home_navigation_enabled:
        return replace(rtf, home_route=None, home_prep=None)
    if rtf.home_route is not None:
        return rtf
    plan = resolve_farm_return_plan(rtf.active_farm_map)
    if plan is None:
        return rtf
    merged_prep = rtf.home_prep if rtf.home_prep is not None else plan.home_prep
    return replace(
        rtf,
        home_route=plan.as_home_route_config(),
        home_prep=merged_prep,
    )
