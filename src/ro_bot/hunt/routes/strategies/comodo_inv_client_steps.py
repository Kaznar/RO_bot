"""Inventory / Kafra storage using **client pixels** (game window coordinates).

``AimService.click_client_pixel`` / ``drag_client_pixels`` convert client (0,0)
= top-left of the **client area** to screen via ``WindowRect``. Use
``client=(x,y)`` from ``input_capture`` (not ``screen=``).

Deposit tabs → storage leave the **storage window open** for
:func:`comodo_inv_withdraw_storage_potions_client_steps`; that function closes
HUD (Alt+E + LMB). World / NPC legs stay ``click_cell`` in ``comodo_home_prep``.
"""

from __future__ import annotations

from ro_bot.hunt.config import HomePrepStep

# Deposit (2026-05-11 capture). No full click on same pixel immediately before drag.
_LOOT_TAB_CLIENT: tuple[int, int] = (11, 217)
_LOOT_ITEM_CLIENT: tuple[int, int] = (40, 100)
_STORAGE_FROM_LOOT_CLIENT: tuple[int, int] = (407, 114)

_EQUIP_TAB_CLIENT: tuple[int, int] = (10, 157)
_EQUIP_ITEM_CLIENT: tuple[int, int] = (40, 100)
_STORAGE_FROM_EQUIP_CLIENT: tuple[int, int] = (476, 91)

_CONSUMABLE_TAB_CLIENT: tuple[int, int] = (13, 113)
_CONSUMABLE_ITEM_CLIENT: tuple[int, int] = (40, 100)
_STORAGE_FROM_CONSUMABLE_CLIENT: tuple[int, int] = (482, 95)

# Withdraw: LMB hold on storage slot → drag to inv → release, then qty + Enter.
_STORAGE_POTION_A_CLIENT: tuple[int, int] = (335, 97)  # (340, 129) enable after 85lvl
_STORAGE_POTION_B_CLIENT: tuple[int, int] = (340, 193)
_INVENTORY_WITHDRAW_DROP_CLIENT: tuple[int, int] = (157, 133)
_CLOSE_STORAGE_CLIENT: tuple[int, int] = (513, 514)


def comodo_inv_storage_client_steps() -> tuple[HomePrepStep, ...]:
    """Deposit loot tabs → storage; leaves the Kafra storage window open."""
    return (
        HomePrepStep(
            click_client=_LOOT_TAB_CLIENT,
            key="",
            delay_after_sec=1.0,
        ),
        HomePrepStep(
            click_client=_LOOT_ITEM_CLIENT,
            drag_to_client=_STORAGE_FROM_LOOT_CLIENT,
            click_client_drag_repeat_count=20,
            click_client_drag_repeat_interval_sec=0.38,
            key="enter",
            delay_after_sec=1.2,
        ),
        HomePrepStep(
            click_client=_EQUIP_TAB_CLIENT,
            key="",
            delay_after_sec=1.0,
        ),
        HomePrepStep(
            click_client=_EQUIP_ITEM_CLIENT,
            drag_to_client=_STORAGE_FROM_EQUIP_CLIENT,
            click_client_drag_repeat_count=10,
            click_client_drag_repeat_interval_sec=0.38,
            key="",
            delay_after_sec=1.2,
        ),
        HomePrepStep(
            click_client=_CONSUMABLE_TAB_CLIENT,
            key="",
            delay_after_sec=1.0,
        ),
        HomePrepStep(
            click_client=_CONSUMABLE_ITEM_CLIENT,
            drag_to_client=_STORAGE_FROM_CONSUMABLE_CLIENT,
            click_client_drag_repeat_count=20,
            click_client_drag_repeat_interval_sec=0.38,
            key="enter",
            delay_after_sec=1.2,
        ),
    )


def comodo_inv_withdraw_storage_potions_client_steps() -> tuple[HomePrepStep, ...]:
    """Storage → inv drags, then qty dialogs; Alt+E; close storage."""
    return (
        HomePrepStep(
            click_client=_STORAGE_POTION_A_CLIENT,
            drag_to_client=_INVENTORY_WITHDRAW_DROP_CLIENT,
            key="",
            delay_after_sec=0.45,
        ),
        HomePrepStep(key="1", delay_after_sec=0.12),
        HomePrepStep(key="0", delay_after_sec=0.12),
        HomePrepStep(key="enter", delay_after_sec=0.55),
        HomePrepStep(
            click_client=_STORAGE_POTION_B_CLIENT,
            drag_to_client=_INVENTORY_WITHDRAW_DROP_CLIENT,
            key="",
            delay_after_sec=0.45,
        ),
        HomePrepStep(key="1", delay_after_sec=0.12),
        HomePrepStep(key="enter", delay_after_sec=0.55),
        HomePrepStep(
            key="e",
            hold_modifiers=("alt",),
            delay_after_sec=1.2,
        ),
        HomePrepStep(
            click_client=_CLOSE_STORAGE_CLIENT,
            key="",
            delay_after_sec=1.0,
        ),
    )
