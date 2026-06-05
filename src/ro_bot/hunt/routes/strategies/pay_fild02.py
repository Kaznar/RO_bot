"""Registered strategy for ``active_farm_map == pay_fild02`` (Comodo town loop)."""

from __future__ import annotations

from ro_bot.hunt.routes.plan import FarmReturnPlan
from ro_bot.hunt.routes.segments.comodo import ComodoPaths
from ro_bot.hunt.routes.segments.pay_fild02 import PayFild02Paths
from ro_bot.hunt.routes.strategies.comodo_home_prep import home_prep_comodo_pay_fild02

# Open Warp menu: tune arrow count until ``pay_fild02`` is selected.
_PAY_FILD02_SKILL_WARP_MENU: tuple[tuple[str, float], ...] = (
    ("down", 0.5),
    ("enter", 1.5),
)


def plan_return_comodo_to_pay_fild02() -> FarmReturnPlan:
    """Comodo restock + healer + skill warp ``x`` → ``pay_fild02``."""
    return FarmReturnPlan(
        home_map=ComodoPaths.HOME_MAP,
        waypoints=PayFild02Paths.after_comodo_skill_warp(),
        click_cooldown_sec=0.0,
        arrival_radius_cells=3,
        home_prep=home_prep_comodo_pay_fild02(
            skill_warp_menu_keys=_PAY_FILD02_SKILL_WARP_MENU,
        ),
    ).assert_targets_farm("pay_fild02")
