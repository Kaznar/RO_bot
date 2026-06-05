"""Config-driven Comodo restock + skill warp (no per-farm registry entry)."""

from __future__ import annotations

import logging
from dataclasses import replace

from ro_bot.hunt.config import (
    FarmHomeRouteConfig,
    FarmRouteWaypoint,
    ReturnToFarmConfig,
)
from ro_bot.hunt.routes.strategies.comodo_home_prep import (
    home_prep_comodo_pay_fild02,
)

logger = logging.getLogger("ro_bot.hunt")

_DEFAULT_SKILL_WARP_MENU: tuple[tuple[str, float], ...] = (
    ("down", 0.5),
    ("enter", 1.5),
)

_HOME_STUB_CELL = (200, 150)
_FARM_STUB_CELL = (100, 100)


def resolve_home_map(rtf: ReturnToFarmConfig) -> str:
    explicit = (rtf.home_map or "").strip()
    if explicit:
        return explicit
    hr = rtf.home_route
    if hr is None:
        return ""
    return (hr.home_map or "").strip()


def has_skill_warp_restock(rtf: ReturnToFarmConfig | None) -> bool:
    if rtf is None:
        return False
    prep = rtf.home_prep
    return prep is not None and prep.enabled and bool(prep.steps)


def ensure_home_route_for_skill_warp(
    rtf: ReturnToFarmConfig,
) -> ReturnToFarmConfig:
    if rtf.home_route is not None:
        return rtf
    if not has_skill_warp_restock(rtf):
        return rtf
    home = resolve_home_map(rtf)
    farm = (rtf.active_farm_map or "").strip()
    if not home or not farm:
        logger.warning(
            "Skill-warp restock: need return_to_farm.home_map and "
            "active_farm_map (got home=%r farm=%r)",
            home or None, farm or None,
        )
        return rtf
    route = FarmHomeRouteConfig(
        home_map=home,
        waypoints=(
            FarmRouteWaypoint(home, *_HOME_STUB_CELL),
            FarmRouteWaypoint(farm, *_FARM_STUB_CELL),
        ),
        finish_on_active_farm_map=True,
        enabled=True,
        click_cooldown_sec=0.0,
        arrival_radius_cells=3,
    )
    logger.info(
        "Skill-warp restock: stub home_route %s → %s (warp in home_prep)",
        home, farm,
    )
    return replace(rtf, home_route=route)


def build_comodo_skill_warp_prep(
    menu_keys: tuple[tuple[str, float], ...] | None = None,
):
    keys = menu_keys if menu_keys else _DEFAULT_SKILL_WARP_MENU
    return home_prep_comodo_pay_fild02(skill_warp_menu_keys=keys)
