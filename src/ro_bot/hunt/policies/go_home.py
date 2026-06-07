"""Return-to-save-point: one item hotkey or a skill + menu sequence."""

from __future__ import annotations

import logging
import time

from ro_bot.core.chat_probe import is_chat_input_visible
from ro_bot.core.hid.bridge import HidBridge
from ro_bot.hunt.config import GoHomeConfig

logger = logging.getLogger("ro_bot.hunt")

_MIN_STEP_GAP_SEC = 0.8


def go_home_configured(cfg: GoHomeConfig | None) -> bool:
    if cfg is None:
        return False
    if cfg.method == "skill":
        return bool(cfg.skill_key.strip())
    return bool(cfg.item_key.strip())


def _step_gap(cfg: GoHomeConfig, extra: float = 0.0) -> float:
    return max(_MIN_STEP_GAP_SEC, cfg.step_delay_sec, extra)


def _maybe_prepend_sp_regen(
    cfg: GoHomeConfig,
    current_sp: int | None,
    sequence: list[tuple[str, float]],
) -> None:
    key = cfg.sp_regen_item_key.strip()
    if not key or current_sp is None:
        return
    if current_sp >= cfg.skill_min_sp:
        return
    gap = _step_gap(cfg)
    sequence.insert(0, (key, gap))
    logger.info(
        "Go home: SP=%d < %d — will press %r before skill",
        current_sp, cfg.skill_min_sp, key,
    )


def _maybe_prepend_chat_dismiss(
    bridge: HidBridge,
    cfg: GoHomeConfig,
    *,
    game_hwnd: int | None,
    sequence: list[tuple[str, float]],
) -> None:
    probe = cfg.dismiss_chat_probe_client
    if probe is None:
        return
    if game_hwnd is None:
        logger.warning(
            "Go home: chat probe configured at %s but no game hwnd — skipped",
            probe,
        )
        return
    visible = is_chat_input_visible(
        game_hwnd,
        probe,
        min_channel=cfg.dismiss_chat_min_channel,
    )
    if visible is not True:
        return
    dismiss = (cfg.dismiss_chat_key or "escape").strip() or "escape"
    gap = _step_gap(cfg)
    sequence.insert(0, (dismiss, gap))
    logger.info(
        "Go home: chat open at client=%s — will press %r before skill",
        probe, dismiss,
    )


def _run_key_sequence(
    bridge: HidBridge,
    sequence: list[tuple[str, float]],
) -> None:
    for key, wait_after in sequence:
        bridge.press_key(key)
        if wait_after > 0:
            time.sleep(wait_after)


def execute_go_home(
    bridge: HidBridge,
    cfg: GoHomeConfig,
    *,
    game_hwnd: int | None = None,
    current_sp: int | None = None,
) -> None:
    """Single item press or cast ``skill_key`` then ``menu`` keys with delays."""
    if cfg.method == "skill":
        skill = cfg.skill_key.strip()
        if not skill:
            return
        sequence: list[tuple[str, float]] = [
            (skill, _step_gap(cfg, cfg.skill_delay_sec)),
        ]
        for key, after in cfg.menu:
            k = key.strip()
            if not k:
                continue
            sequence.append((k, _step_gap(cfg, after)))
        _maybe_prepend_sp_regen(cfg, current_sp, sequence)
        _maybe_prepend_chat_dismiss(
            bridge, cfg, game_hwnd=game_hwnd, sequence=sequence,
        )
        _run_key_sequence(bridge, sequence)
        logger.warning(
            "Go home: skill %r + %d menu key(s) (%d step(s) total)",
            skill, len(cfg.menu), len(sequence),
        )
        return
    item = cfg.item_key.strip()
    if not item:
        return
    bridge.press_key(item)
    logger.warning("Go home: item %r", item)
