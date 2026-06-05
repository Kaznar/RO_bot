"""Return-to-save-point: one item hotkey or a skill + menu sequence."""

from __future__ import annotations

import logging
import time

from ro_bot.core.hid.bridge import HidBridge
from ro_bot.hunt.config import GoHomeConfig

logger = logging.getLogger("ro_bot.hunt")


def go_home_configured(cfg: GoHomeConfig | None) -> bool:
    if cfg is None:
        return False
    if cfg.method == "skill":
        return bool(cfg.skill_key.strip())
    return bool(cfg.item_key.strip())


def execute_go_home(bridge: HidBridge, cfg: GoHomeConfig) -> None:
    """Single item press or cast ``skill_key`` then ``menu`` keys with delays."""
    if cfg.method == "skill":
        skill = cfg.skill_key.strip()
        if not skill:
            return
        bridge.press_key(skill)
        delay = cfg.skill_delay_sec
        if delay > 0:
            time.sleep(delay)
        for key, after in cfg.menu:
            k = key.strip()
            if not k:
                continue
            bridge.press_key(k)
            if after > 0:
                time.sleep(after)
        logger.warning(
            "Go home: skill %r + %d menu key(s)",
            skill, len(cfg.menu),
        )
        return
    item = cfg.item_key.strip()
    if not item:
        return
    bridge.press_key(item)
    logger.warning("Go home: item %r", item)
