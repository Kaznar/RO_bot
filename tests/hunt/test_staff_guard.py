"""Staff guard detection."""

from __future__ import annotations

from unittest.mock import MagicMock

from ro_bot.core.network.sniffer import EntityState
from ro_bot.hunt.config import StaffGuardConfig
from ro_bot.hunt.policies.staff_guard import (
    StaffGuardPolicy,
    is_staff_entity,
)


def test_gid_and_name_detection() -> None:
    cfg = StaffGuardConfig()
    assert is_staff_entity(EntityState(gid=2_000_001, name="GM Star"), cfg)
    assert is_staff_entity(EntityState(gid=100, name="Admin Bob"), cfg)
    assert not is_staff_entity(EntityState(gid=100, name="Poring"), cfg)
    assert not is_staff_entity(EntityState(gid=110_112_620, name="Cruiser"), cfg)
    assert not is_staff_entity(EntityState(gid=2_600_000, name="Someone"), cfg)


def test_closes_on_hunt_map_not_town() -> None:
    sniffer = MagicMock()
    sniffer.get_all_entities.return_value = [
        EntityState(gid=2_000_001, name="GM Star", x=102, y=80),
        EntityState(gid=110_112_620, name="Cruiser", x=99, y=22),
    ]
    policy = StaffGuardPolicy(
        StaffGuardConfig(max_distance_cells=5),
        sniffer,
        frozenset({"comodo"}),
        game_hwnd=0,
    )
    assert not policy.check("comodo", (100, 78))
    assert policy.check("prt_fild03", (100, 78))


def test_closes_on_home_map_even_if_manual_control() -> None:
    sniffer = MagicMock()
    sniffer.get_all_entities.return_value = [
        EntityState(gid=2_000_001, name="GM Star", x=148, y=130),
    ]
    policy = StaffGuardPolicy(
        StaffGuardConfig(max_distance_cells=20),
        sniffer,
        frozenset({"xmas", "comodo"}),
        home_map="xmas",
        game_hwnd=0,
    )
    assert not policy.check("comodo", (148, 129))
    assert policy.check("xmas", (148, 129))
