"""Aldebaran ``home_prep`` — Kafra storage, healer, Kafra warp (no walk)."""

from __future__ import annotations

from dataclasses import replace

from ro_bot.hunt.config import HomePrepConfig, HomePrepStep
from ro_bot.hunt.routes.town import (
    Healer,
    Kafra,
    close_storage_steps,
    deposit_to_storage_steps,
    withdraw_from_storage_slots,
)

_SETTLE_AFTER_HOME_WARP_SEC = 3.0
_DELAY_BEFORE_NPC_SEC = 1.0
_DELAY_AFTER_HEALER_BEFORE_KAFRA_SEC = 4.5

_CHAT_INPUT_PROBE_CLIENT: tuple[int, int] | None = (176, 887)

_KAFRA = Kafra((143, 120), default_click_delay_sec=1.43)
_HEALER = Healer((136, 120))

# Mjolnir field warp menu — only the trailing arrow block varies between towns.
_MJOLNIR_WARP_KEYS: tuple[tuple[str, float], ...] = (
    ("enter", 1.0),
    ("down", 1.0),
    ("down", 1.0),
    ("down", 1.0),
    ("enter", 2.0),
    ("enter", 2.0),
    ("down", 1.0),
    ("down", 1.0),
    ("down", 1.0),
    ("enter", 2.0),
)


def home_prep_aldebaran() -> HomePrepConfig:
    """Aldebaran save → Kafra storage → healer → Kafra warp to farm."""
    warp_raw = _KAFRA.warp_from_npc_steps(
        _MJOLNIR_WARP_KEYS,
        lead_clicks=2,
        click_delay_sec=1.5,
    )
    warp = (replace(warp_raw[0], kafra_warp_retry_anchor=True),) + warp_raw[1:]
    return HomePrepConfig(
        enabled=True,
        max_total_sec=180.0,
        finish_when_weight_ratio_below=0.0,
        retry_kafra_warp_until_farm_map=True,
        kafra_warp_max_retries=3,
        steps=(
            HomePrepStep(
                key="",
                delay_after_sec=_SETTLE_AFTER_HOME_WARP_SEC,
            ),
            HomePrepStep(
                key="",
                delay_after_sec=_DELAY_BEFORE_NPC_SEC,
            ),
            *_KAFRA.open_storage_menu_steps(),
            HomePrepStep(
                key="e",
                hold_modifiers=("alt",),
                delay_after_sec=1.5,
            ),
            *deposit_to_storage_steps(),
            #*withdraw_from_storage_slots(),
            *close_storage_steps(),
            HomePrepStep(
                key="",
                dismiss_chat_probe_client=_CHAT_INPUT_PROBE_CLIENT,
                dismiss_chat_min_channel=228,
                dismiss_chat_key="esc",
                delay_after_sec=1.0,
            ),
            *_HEALER.heal_dialog_steps(delays_sec=(1.0, 1.0, 2.0)),
            HomePrepStep(
                key="",
                delay_after_sec=_DELAY_AFTER_HEALER_BEFORE_KAFRA_SEC,
                healer_buff_done=True,
            ),
            *warp,
            HomePrepStep(
                key="",
                dismiss_chat_probe_client=_CHAT_INPUT_PROBE_CLIENT,
                dismiss_chat_min_channel=228,
                dismiss_chat_key="esc",
                delay_after_sec=1.0,
            ),
        ),
        post_steps=(),
    )
