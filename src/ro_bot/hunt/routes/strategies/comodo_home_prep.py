"""Comodo town ``home_prep`` — Kafra + inventory/storage (client pixels).

Deposit / withdraw / fish shop HUD use ``click_client`` modules; walk to the
vendor uses ``click_cell``. See :mod:`comodo_inv_client_steps` and
:mod:`comodo_fish_shop_client_steps`.

Heal/buffer omitted.
"""

from __future__ import annotations

from ro_bot.hunt.config import HomePrepConfig, HomePrepStep
from ro_bot.hunt.routes.strategies.comodo_fish_shop_client_steps import (
    comodo_fish_shop_client_steps,
)
from ro_bot.hunt.routes.strategies.comodo_inv_client_steps import (
    comodo_inv_storage_client_steps,
    comodo_inv_withdraw_storage_potions_client_steps,
)

_KAFRA_CELL = (195, 150)


_SETTLE_AFTER_HOME_WARP_SEC = 3.0
_DELAY_AFTER_STAND_BEFORE_KAFRA_SEC = 3.92

# Client pixel inside the white chat input when open (from input-capture).
_COMODO_SPACE_AFTER_INV_PROBE: tuple[int, int] | None = (42, 889)


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
            HomePrepStep(key="space", delay_after_sec=0.55),
            HomePrepStep(
                key="",
                delay_after_sec=_DELAY_AFTER_STAND_BEFORE_KAFRA_SEC,
            ),
            HomePrepStep(click_cell=_KAFRA_CELL, key="", delay_after_sec=1.43),
            HomePrepStep(key="enter", delay_after_sec=0.55),
            HomePrepStep(key="down", delay_after_sec=0.43),
            HomePrepStep(key="enter", delay_after_sec=0.48),
            HomePrepStep(key="enter", delay_after_sec=1.0),
            HomePrepStep(
                key="e",
                hold_modifiers=("alt",),
                delay_after_sec=1.5,
            ),
            *comodo_inv_storage_client_steps(),
            *comodo_inv_withdraw_storage_potions_client_steps(),
            HomePrepStep(
                key="space",
                dismiss_chat_probe_client=_COMODO_SPACE_AFTER_INV_PROBE,
                dismiss_chat_min_channel=228,
                dismiss_chat_key="esc",
                delay_after_sec=0.55,
            ),
            HomePrepStep(
                click_cell=(217, 152),
                key="",
                delay_after_sec=5.0,
            ),
            *comodo_fish_shop_client_steps(),
            HomePrepStep(
                click_cell=(200, 150),
                key="enter",
                delay_after_sec=1.0,
            ),
            HomePrepStep(key="enter", delay_after_sec=0.55),
            HomePrepStep(key="enter", delay_after_sec=0.55),
        ),
        post_steps=(),
    )
