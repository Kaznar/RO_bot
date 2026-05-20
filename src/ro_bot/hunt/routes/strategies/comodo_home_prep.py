"""Comodo town ``home_prep`` — Kafra + inventory/storage (client pixels)."""

from __future__ import annotations

from ro_bot.hunt.config import HomePrepConfig, HomePrepStep
from ro_bot.hunt.routes.strategies.comodo_fish_shop_client_steps import (
    comodo_fish_shop_client_steps,
)
from ro_bot.hunt.routes.town import Kafra, deposit_to_storage_steps, withdraw_from_storage_slots

_SETTLE_AFTER_HOME_WARP_SEC = 3.0
_DELAY_AFTER_STAND_BEFORE_KAFRA_SEC = 3.92

_COMODO_SPACE_AFTER_INV_PROBE: tuple[int, int] | None = (176, 887)

_KAFRA = Kafra((195, 150))


def home_prep_comodo() -> HomePrepConfig:
    """Kafra + Alt+E, deposit, withdraw potions, fish shop (client HUD)."""
    return HomePrepConfig(
        enabled=True,
        max_total_sec=180.0,
        finish_when_weight_ratio_below=0.0,
        steps=(
            HomePrepStep(
                key="",
                delay_after_sec=_SETTLE_AFTER_HOME_WARP_SEC,
            ),
            HomePrepStep(key="space", delay_after_sec=1.0),
            HomePrepStep(
                key="",
                delay_after_sec=_DELAY_AFTER_STAND_BEFORE_KAFRA_SEC,
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
                key="space",
                dismiss_chat_probe_client=_COMODO_SPACE_AFTER_INV_PROBE,
                dismiss_chat_min_channel=228,
                dismiss_chat_key="esc",
                delay_after_sec=1.0,
            ),
            HomePrepStep(
                click_cell=(214, 152),
                key="",
                delay_after_sec=5.0,
            ),
            *comodo_fish_shop_client_steps(),
            HomePrepStep(
                click_cell=(200, 150),
                key="enter",
                delay_after_sec=2.0,
            ),
            HomePrepStep(key="enter", delay_after_sec=2.0),
            HomePrepStep(key="enter", delay_after_sec=2.0),
        ),
        post_steps=(),
    )
