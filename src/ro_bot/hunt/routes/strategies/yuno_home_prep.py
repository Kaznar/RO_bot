"""Yuno ``home_prep`` — Kafra storage, healer (no field warp)."""

from __future__ import annotations

from ro_bot.hunt.config import HomePrepConfig, HomePrepStep
from ro_bot.hunt.routes.town import (
    Healer,
    Kafra,
    deposit_to_storage_steps,
    withdraw_from_storage_slots,
)

_SETTLE_AFTER_HOME_WARP_SEC = 3.0
_DELAY_BEFORE_NPC_SEC = 1.0
_DELAY_AFTER_HEALER_SEC = 1.0

_CHAT_INPUT_PROBE_CLIENT: tuple[int, int] | None = (176, 887)

_KAFRA = Kafra((152, 187))
_HEALER = Healer((146, 187))


def home_prep_yuno() -> HomePrepConfig:
    """Yuno save → Kafra deposit/withdraw → healer (walk to farm via home route)."""
    return HomePrepConfig(
        enabled=True,
        max_total_sec=180.0,
        finish_when_weight_ratio_below=0.0,
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
            *withdraw_from_storage_slots(),
            HomePrepStep(
                key="",
                dismiss_chat_probe_client=_CHAT_INPUT_PROBE_CLIENT,
                dismiss_chat_min_channel=228,
                dismiss_chat_key="esc",
                delay_after_sec=1.0,
            ),
            *_HEALER.heal_dialog_steps(delays_sec=(1.0, 1.0, 2.0)),
            HomePrepStep(
                key="enter",
                delay_after_sec=1.0,
            ),
            HomePrepStep(
                key="",
                dismiss_chat_probe_client=_CHAT_INPUT_PROBE_CLIENT,
                dismiss_chat_min_channel=228,
                dismiss_chat_key="esc",
                delay_after_sec=1.0,
            ),
            HomePrepStep(
                key="",
                delay_after_sec=_DELAY_AFTER_HEALER_SEC,
                healer_buff_done=True,
            ),
        ),
        post_steps=(),
    )
