"""Compatibility re-exports — see :mod:`ro_bot.hunt.routes.town.storage_hud`."""

from __future__ import annotations

from ro_bot.hunt.routes.town.storage_hud import (
    comodo_inv_storage_client_steps,
    comodo_inv_withdraw_storage_potions_client_steps,
    deposit_to_storage_steps,
    withdraw_from_storage_slots,
)

__all__ = [
    "comodo_inv_storage_client_steps",
    "comodo_inv_withdraw_storage_potions_client_steps",
    "deposit_to_storage_steps",
    "withdraw_from_storage_slots",
]
