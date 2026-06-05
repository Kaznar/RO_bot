"""Config-driven skill-warp restock (no per-farm registry)."""

from __future__ import annotations

from ro_bot.app.config.loader import _parse_return_to_farm
from ro_bot.hunt.routes.registry import augment_return_to_farm_from_registry
from ro_bot.hunt.routes.skill_warp_restock import resolve_home_map


def test_preset_enables_home_prep_and_stub_route(tmp_path) -> None:
    rtf = _parse_return_to_farm(
        {
            "home_map": "comodo",
            "home_prep_preset": "comodo_skill_warp",
            "skill_warp_menu": [["down", 1.0], ["enter", 2.0]],
            "active_farm_map": "prt_fild03",
            "maps": {},
        },
        "profile.return_to_farm",
        config_dir=tmp_path,
    )
    assert rtf is not None
    assert rtf.home_prep is not None
    assert rtf.home_prep.enabled
    assert len(rtf.home_prep.steps) > 0

    merged = augment_return_to_farm_from_registry(rtf)
    assert merged is not None
    assert merged.home_route is not None
    assert merged.home_route.home_map == "comodo"
    assert merged.home_route.waypoints[-1].map_name == "prt_fild03"
    assert resolve_home_map(merged) == "comodo"


def test_preset_disabled_uses_registry_not_skill_warp(tmp_path) -> None:
    rtf = _parse_return_to_farm(
        {
            "home_map": "xmas",
            "home_prep_preset": "comodo_skill_warp",
            "home_prep_preset_enabled": False,
            "skill_warp_menu": [["down", 0.5], ["enter", 1.5]],
            "active_farm_map": "xmas_dun02",
            "maps": {},
        },
        "profile.return_to_farm",
        config_dir=tmp_path,
    )
    assert rtf is not None
    assert rtf.home_prep is None

    merged = augment_return_to_farm_from_registry(rtf)
    assert merged is not None
    assert merged.home_prep is not None
    assert merged.home_route is not None
    assert merged.home_route.home_map == "xmas"
    assert merged.home_route.waypoints[-1].map_name == "xmas_dun02"
