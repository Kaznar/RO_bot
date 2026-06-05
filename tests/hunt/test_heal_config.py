"""Heal config parsing and channel ordering."""

from __future__ import annotations

from ro_bot.app.config.loader import _parse_heal
from ro_bot.hunt.config import HealChannelConfig, HealConfig
from ro_bot.hunt.policies.heal import _build_channel_list


def test_parse_dual_channels() -> None:
    cfg = _parse_heal(
        {
            "item": {"keys": ["h"], "min_hp": 1000, "cooldown_sec": 0.3},
            "skill": {
                "keys": ["s"],
                "min_hp": 500,
                "cooldown_sec": 0.2,
                "click_self": True,
            },
            "save_recovery_key": "h",
        },
        "profile.heal",
    )
    assert cfg is not None
    assert cfg.item is not None
    assert cfg.item.min_hp == 1000
    assert cfg.skill is not None
    assert cfg.skill.min_hp == 500
    assert cfg.skill.click_self is True


def test_parse_legacy_flat_as_skill() -> None:
    cfg = _parse_heal(
        {"keys": ["s"], "min_hp": 500, "click_self": True},
        "profile.heal",
    )
    assert cfg is not None
    assert cfg.item is None
    assert cfg.skill is not None
    assert cfg.skill.keys == ("s",)
    assert cfg.skill.min_hp == 500


def test_channel_order_higher_threshold_first() -> None:
    cfg = HealConfig(
        item=HealChannelConfig(keys=("h",), min_hp=1000),
        skill=HealChannelConfig(keys=("s",), min_hp=500),
    )
    names = [n for n, _ in _build_channel_list(cfg)]
    assert names == ["item", "skill"]
