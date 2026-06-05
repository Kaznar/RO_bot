"""Comodo town ``home_prep`` — Kafra, healer, skill warp back to farm."""

from __future__ import annotations

from ro_bot.hunt.config import HomePrepConfig, HomePrepStep
from ro_bot.hunt.routes.strategies.comodo_fish_shop_client_steps import (
    comodo_fish_shop_client_steps,
)
from ro_bot.hunt.routes.town import (
    Healer,
    Kafra,
    close_storage_steps,
    deposit_to_storage_steps,
)
from ro_bot.hunt.routes.town.skill_warp import skill_warp_steps

_SETTLE_AFTER_HOME_WARP_SEC = 3.0
_DELAY_AFTER_STAND_BEFORE_KAFRA_SEC = 3.92
_DELAY_AFTER_HEALER_SEC = 1.0

_COMODO_SPACE_AFTER_INV_PROBE: tuple[int, int] | None = (176, 887)

# Open Warp: cast / portal cell one step east of the player (tune if needed).
_COMODO_SKILL_WARP_CAST_OFFSET: tuple[float, float] = (1.0, 0.0)

# beach_dun3 via Open Warp (cmd / um field routes).
_BEACH_DUN3_SKILL_WARP_MENU: tuple[tuple[str, float], ...] = (
    ("down", 1.5),
    ("enter", 1.5),
)

_KAFRA = Kafra((195, 150))
_COMODO_HEALER_CELL = (200, 150)
_HEALER = Healer(_COMODO_HEALER_CELL)


def _comodo_kafra_storage_steps() -> tuple[HomePrepStep, ...]:
    return (
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
        #*withdraw_from_storage_slots(),
        *close_storage_steps(),
        HomePrepStep(
            key="space",
            dismiss_chat_probe_client=_COMODO_SPACE_AFTER_INV_PROBE,
            dismiss_chat_min_channel=228,
            dismiss_chat_key="esc",
            delay_after_sec=1.0,
        ),
    )


def _comodo_healer_steps() -> tuple[HomePrepStep, ...]:
    return (
        HomePrepStep(
            click_cell=_COMODO_HEALER_CELL,
            key="",
            delay_after_sec=5.0,
        ),
        *_HEALER.heal_dialog_steps(delays_sec=(1.0, 1.0, 2.0)),
        HomePrepStep(key="enter", delay_after_sec=1.0),
        HomePrepStep(
            key="",
            dismiss_chat_probe_client=_COMODO_SPACE_AFTER_INV_PROBE,
            dismiss_chat_min_channel=228,
            dismiss_chat_key="esc",
            delay_after_sec=1.0,
        ),
        HomePrepStep(
            key="",
            delay_after_sec=_DELAY_AFTER_HEALER_SEC,
            healer_buff_done=True,
        ),
    )


def home_prep_comodo_pay_fild02(
    *,
    skill_warp_menu_keys: tuple[tuple[str, float], ...],
) -> HomePrepConfig:
    """Kafra, healer, Open Warp ``x`` — ``skill_warp_menu_keys`` selects farm map."""
    return HomePrepConfig(
        enabled=True,
        max_total_sec=180.0,
        finish_when_weight_ratio_below=0.0,
        steps=(
            *_comodo_kafra_storage_steps(),
            *_comodo_healer_steps(),
            *skill_warp_steps(
                cast_key="x",
                cast_cell_offset=_COMODO_SKILL_WARP_CAST_OFFSET,
                cast_delay_after_sec=1.0,
                menu_keys=skill_warp_menu_keys,
                enter_portal_delay_after_sec=3.0,
            ),
        ),
        post_steps=(),
    )


def home_prep_comodo() -> HomePrepConfig:
    """Kafra, optional fish shop, skill warp toward beach_dun3 (cmd / um routes)."""
    return HomePrepConfig(
        enabled=True,
        max_total_sec=180.0,
        finish_when_weight_ratio_below=0.0,
        steps=(
            *_comodo_kafra_storage_steps(),
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
            *skill_warp_steps(
                cast_key="x",
                cast_cell_offset=_COMODO_SKILL_WARP_CAST_OFFSET,
                cast_delay_after_sec=2.0,
                menu_keys=_BEACH_DUN3_SKILL_WARP_MENU,
                enter_portal_delay_after_sec=3.0,
            ),
        ),
        post_steps=(),
    )
