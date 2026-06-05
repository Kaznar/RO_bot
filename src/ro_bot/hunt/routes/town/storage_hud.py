"""Kafra storage / inventory HUD — client pixels (global for this game client).

Town world positions use :class:`~ro_bot.hunt.config.HomePrepStep` ``click_cell``;
this module is **only** client-space pixels (tabs, storage grid, drag targets).

Withdraw slots are addressed by **row index** (0 = top calibrated data row) and
optional column (0 or 1 for two storage columns).
"""

from __future__ import annotations

from dataclasses import dataclass

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

_INVENTORY_WITHDRAW_DROP_CLIENT: tuple[int, int] = (157, 133)
_CLOSE_STORAGE_CLIENT: tuple[int, int] = (513, 514)


@dataclass(frozen=True)
class StorageWithdrawGrid:
    """Mapping from logical storage row/column to client pixel (slot centre)."""

    col_xs: tuple[int, int]
    row0_y: int
    row_pitch_px: int = 32

    def slot_client(self, row: int, col: int = 0) -> tuple[int, int]:
        if col not in (0, 1):
            raise ValueError("col must be 0 or 1")
        y = self.row0_y + row * self.row_pitch_px
        return (self.col_xs[col], y)


# Row index 1 col 0 capture: client=(329, 94) (2026-05-15). First row = one pitch up.
_DEFAULT_GRID = StorageWithdrawGrid(
    col_xs=(335, 335),
    row0_y=62,
    row_pitch_px=34,
)

# Default home-prep withdraw profile (**all towns** share this HUD).
# Change rows/columns/qty keys here only — not per-city modules.
DEFAULT_HOME_PREP_WITHDRAW_SLOTS: tuple[tuple[int, int, tuple[str, ...]], ...] = (
    (5, 0, ("3", "enter")),
    (9, 1, ("1", "enter")),
    (12, 1, ("80", "enter")),
)


def inventory_withdraw_drop_client() -> tuple[int, int]:
    return _INVENTORY_WITHDRAW_DROP_CLIENT


def deposit_to_storage_steps() -> tuple[HomePrepStep, ...]:
    """Deposit loot / equip / consumable tabs → storage; leaves storage window open."""
    return (
        HomePrepStep(
            click_client=_LOOT_TAB_CLIENT,
            key="",
            delay_after_sec=1.0,
        ),
        HomePrepStep(
            click_client=_LOOT_ITEM_CLIENT,
            drag_to_client=_STORAGE_FROM_LOOT_CLIENT,
            click_client_drag_repeat_count=10,
            click_client_drag_repeat_interval_sec=0.38,
            key="enter",
            delay_after_sec=1.0,
        ),
        HomePrepStep(
            click_client=_EQUIP_TAB_CLIENT,
            key="",
            delay_after_sec=1.0,
        ),
        HomePrepStep(
            click_client=_EQUIP_ITEM_CLIENT,
            drag_to_client=_STORAGE_FROM_EQUIP_CLIENT,
            click_client_drag_repeat_count=15,
            click_client_drag_repeat_interval_sec=0.38,
            key="",
            delay_after_sec=1.0,
        ),
        HomePrepStep(
            click_client=_CONSUMABLE_TAB_CLIENT,
            key="",
            delay_after_sec=1.0,
        ),
        HomePrepStep(
            click_client=_CONSUMABLE_ITEM_CLIENT,
            drag_to_client=_STORAGE_FROM_CONSUMABLE_CLIENT,
            click_client_drag_repeat_count=10,
            click_client_drag_repeat_interval_sec=0.38,
            key="enter",
            delay_after_sec=1.0,
        ),
    )


def withdraw_from_storage_cell(
    client_xy: tuple[int, int],
    *,
    delay_after_drag_sec: float = 1.0,
) -> tuple[HomePrepStep, ...]:
    """One storage slot → inventory drop (drag only + pause)."""
    return (
        HomePrepStep(
            click_client=client_xy,
            drag_to_client=_INVENTORY_WITHDRAW_DROP_CLIENT,
            key="",
            delay_after_sec=delay_after_drag_sec,
        ),
    )


def _keys_to_steps(keys: tuple[str, ...], delays: tuple[float, ...]) -> tuple[HomePrepStep, ...]:
    if len(keys) != len(delays):
        raise ValueError("keys and delays length mismatch")
    return tuple(
        HomePrepStep(key=k, delay_after_sec=d)
        for k, d in zip(keys, delays, strict=True)
    )


def _expand_qty_keys(keys: tuple[str, ...]) -> tuple[str, ...]:
    """Split multi-digit numeric tokens into per-character key presses.

    The HID layer (:meth:`HidBridge.press_key`) only accepts a single
    character or a named key (``"enter"``, ``"space"``, …). Withdraw-qty
    profiles however want to read like decimal numbers (``"80"``), so any
    purely numeric token longer than one character is split into single
    digits. Named keys and single-character tokens pass through unchanged.
    """
    out: list[str] = []
    for k in keys:
        if len(k) > 1 and k.isdigit():
            out.extend(k)
        else:
            out.append(k)
    return tuple(out)


def withdraw_storage_row(
    row: int,
    *,
    col: int = 0,
    grid: StorageWithdrawGrid | None = None,
    qty_keys: tuple[str, ...] = ("1", "enter"),
    key_delays: tuple[float, ...] | None = None,
) -> tuple[HomePrepStep, ...]:
    """Withdraw one stack from a grid row (0-based). Default qty = pick 1 + confirm.

    Multi-digit numeric tokens in ``qty_keys`` (e.g. ``"80"``) are expanded
    into single-digit presses before timing is applied; ``key_delays``, when
    supplied, must match the expanded length.
    """
    g = grid or _DEFAULT_GRID
    cell = g.slot_client(row, col)
    expanded = _expand_qty_keys(qty_keys)
    if key_delays is None:
        n = len(expanded)
        if n == 1:
            key_delays = (1.0,)
        else:
            key_delays = tuple(0.5 for _ in expanded[:-1]) + (1.0,)
    if len(expanded) != len(key_delays):
        raise ValueError(
            f"qty_keys expanded to {len(expanded)} presses but got "
            f"{len(key_delays)} key_delays (multi-digit numeric tokens "
            f"split per character; original qty_keys={qty_keys})"
        )
    return (
        *withdraw_from_storage_cell(cell),
        *_keys_to_steps(expanded, key_delays),
    )


def close_storage_steps(*, delay_after_sec: float = 1.5) -> tuple[HomePrepStep, ...]:
    """Alt+E then LMB close on Kafra storage chrome (+ pause)."""
    return (
        HomePrepStep(
            key="e",
            hold_modifiers=("alt",),
            delay_after_sec=1.5,
        ),
        HomePrepStep(
            click_client=_CLOSE_STORAGE_CLIENT,
            key="",
            delay_after_sec=delay_after_sec,
        ),
    )


def withdraw_from_storage_slots(
    slots: tuple[tuple[int, int, tuple[str, ...]], ...] | None = None,
    *,
    grid: StorageWithdrawGrid | None = None,
    close_storage: bool = True,
) -> tuple[HomePrepStep, ...]:
    """Withdraw one or more stacks by row/col, then optionally Alt+E + close.

    ``slots`` entries: ``(row, col, qty_key_sequence)``. When ``None``, uses
    :data:`DEFAULT_HOME_PREP_WITHDRAW_SLOTS` (global potion profile for every town).
    """
    spec = DEFAULT_HOME_PREP_WITHDRAW_SLOTS if slots is None else slots
    parts: list[HomePrepStep] = []
    for row, col, qty_keys in spec:
        parts.extend(
            withdraw_storage_row(
                row,
                col=col,
                grid=grid,
                qty_keys=qty_keys,
            ),
        )
    if close_storage:
        parts.extend(close_storage_steps())
    return tuple(parts)


# Backward-compatible names (prefer :func:`deposit_to_storage_steps` / above).
def comodo_inv_storage_client_steps() -> tuple[HomePrepStep, ...]:
    """Deprecated alias — use :func:`deposit_to_storage_steps`."""
    return deposit_to_storage_steps()


def comodo_inv_withdraw_storage_potions_client_steps() -> tuple[HomePrepStep, ...]:
    """Deprecated alias — use :func:`withdraw_from_storage_slots`."""
    return withdraw_from_storage_slots()
