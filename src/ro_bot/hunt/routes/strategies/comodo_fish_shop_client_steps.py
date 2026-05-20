"""Comodo Fresh Fish vendor — HUD ``click_client`` steps from ``input_capture``.

Walking to the NPC stays ``click_cell`` in :mod:`comodo_home_prep`; this module
only covers shop UI after the walk (client pixels).
"""

from __future__ import annotations

from ro_bot.hunt.config import HomePrepStep

# 2026-05-11 capture (client=), po ``click_cell`` walk k NPC.
_FISH_SHOP_DIALOG_CLIENT: tuple[int, int] = (1130, 38)
_FISH_SHOP_BUY_BUTTON_CLIENT: tuple[int, int] = (835, 661)
_FISH_SHOP_FRESH_FISH_CLIENT: tuple[int, int] = (53, 194)
# After qty + Enter — confirm purchase (capture).
_FISH_SHOP_BUY_CONFIRM_CLIENT: tuple[int, int] = (469, 355)
_INV_CELL_CLIENT_PX: int = 26

_FISH_SHOP_DRAG_TO_CLIENT: tuple[int, int] = (
    _FISH_SHOP_BUY_CONFIRM_CLIENT[0],
    _FISH_SHOP_BUY_CONFIRM_CLIENT[1] - _INV_CELL_CLIENT_PX,
)


def comodo_fish_shop_client_steps() -> tuple[HomePrepStep, ...]:
    """Dialog → buy → select fish → drag to buy slot → qty → confirm."""
    return (
        HomePrepStep(
            click_cell=(225, 164),
            key="",
            delay_after_sec=1.0,
        ),
        HomePrepStep(
            click_client=_FISH_SHOP_BUY_BUTTON_CLIENT,
            key="",
            delay_after_sec=1.0,
        ),
        HomePrepStep(
            click_client=_FISH_SHOP_FRESH_FISH_CLIENT,
            key="",
            delay_after_sec=1.0,
        ),
        HomePrepStep(
            click_client=_FISH_SHOP_FRESH_FISH_CLIENT,
            drag_to_client=_FISH_SHOP_DRAG_TO_CLIENT,
            click_client_drag_settle_before_down_sec=0.22,
            click_client_drag_segments=22,
            key="",
            delay_after_sec=1.0,
        ),
        HomePrepStep(key="1", delay_after_sec=0.5),
        #HomePrepStep(key="0", delay_after_sec=0.12),
        HomePrepStep(key="0", delay_after_sec=0.5),
        HomePrepStep(key="enter", delay_after_sec=0.55),
        HomePrepStep(
            click_client=_FISH_SHOP_BUY_CONFIRM_CLIENT,
            key="",
            delay_after_sec=1.0,
        ),
    )
