"""Open Warp (or similar) — cast on a cell beside the player, menu, step in."""

from __future__ import annotations

from ro_bot.hunt.config import HomePrepStep


def skill_warp_steps(
    *,
    cast_key: str = "x",
    cast_cell_offset: tuple[float, float] = (1.0, 0.0),
    cast_delay_after_sec: float = 1.0,
    menu_keys: tuple[tuple[str, float], ...] = (
        ("down", 0.5),
        ("enter", 1.5),
    ),
    enter_portal_delay_after_sec: float = 3.0,
) -> tuple[HomePrepStep, ...]:
    """Press skill, LMB offset cell, menu keys, walk into the portal cell.

    ``cast_cell_offset`` is added to memory ``(x, y)`` for cast and entry clicks
    (one adjacent ground cell). Tune per standing spot and warp facing.
    """
    return (
        HomePrepStep(key=cast_key, delay_after_sec=0.2),
        HomePrepStep(
            click_cell_offset=cast_cell_offset,
            delay_after_sec=cast_delay_after_sec,
        ),
        *(HomePrepStep(key=k, delay_after_sec=d) for k, d in menu_keys),
        HomePrepStep(
            click_cell_offset=cast_cell_offset,
            delay_after_sec=enter_portal_delay_after_sec,
        ),
    )
