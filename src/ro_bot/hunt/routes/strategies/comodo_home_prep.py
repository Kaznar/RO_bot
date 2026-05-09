"""Comodo town ``home_prep`` — explicit HID steps (no client macro).

Steps 1–9: settle, stand, Kafra dialog, Alt+E — **frozen** for now.
Step 10: one world click on ``comodo``; sequence **ends** there until
more steps are added (you guide step-by-step).

Heal/buffer omitted.
"""

from __future__ import annotations

from ro_bot.hunt.config import HomePrepConfig, HomePrepStep

_KAFRA_CELL = (195, 150)

_SETTLE_AFTER_HOME_WARP_SEC = 3.0
_DELAY_AFTER_STAND_BEFORE_KAFRA_SEC = 3.92

# Client pixel inside the white chat input when open — z ``input-capture``
# (JoJo / NexusRO client cca 1600×900): ``client=(42, 889)``.
_COMODO_SPACE_AFTER_INV_PROBE: tuple[int, int] | None = (42, 889)


def home_prep_comodo() -> HomePrepConfig:
    """Kafra + Alt+E, then step-10 world click; prep stops (no post_steps)."""
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
                # Open inventory
                key="e",
                hold_modifiers=("alt",),
                delay_after_sec=1.5,
            ),
            HomePrepStep(
                click_cell=(192.3, 144),
                key="",
                delay_after_sec=1.0,
            ),
            HomePrepStep(
                # Loot to storage
                click_cell=(193.3, 147.8),
                click_cell_drag_to=(200, 147.8),
                click_cell_drag_repeat_count=30,
                click_cell_drag_repeat_interval_sec=0.38,
                key="enter",
                delay_after_sec=1.2,
            ),
            HomePrepStep(
                click_cell=(192.3, 146),
                key="",
                delay_after_sec=1.0,
            ),
            HomePrepStep(
                # Equip to storage
                click_cell=(193.3, 147.8),
                click_cell_drag_to=(200, 147.8),
                click_cell_drag_repeat_count=30,
                click_cell_drag_repeat_interval_sec=0.38,
                key="",
                delay_after_sec=1.2,
            ),
            HomePrepStep(
                click_cell=(192.3, 147),
                key="",
                delay_after_sec=1.0,
            ),
            HomePrepStep(
                # Consume to storage
                click_cell=(194.8, 147.8),
                click_cell_drag_to=(200, 147.8),
                click_cell_drag_repeat_count=30,
                click_cell_drag_repeat_interval_sec=0.38,
                key="enter",
                delay_after_sec=1.2,
            ),
            HomePrepStep(
                click_cell=(200, 147.8),
                key="",
                delay_after_sec=1.0,
            ),
            HomePrepStep(
                # Bersekr potion from storage
                click_cell=(196.5, 146.5),
                click_cell_drag_to=(194, 146.5),
                click_cell_drag_repeat_count=1,
                click_cell_drag_repeat_interval_sec=0.38,
                key="",
                delay_after_sec=0.45,
            ),
            HomePrepStep(key="1", delay_after_sec=0.12),
            HomePrepStep(key="0", delay_after_sec=0.12),
            HomePrepStep(key="enter", delay_after_sec=1.2),
            HomePrepStep(
                # Butterfly Wing from storage
                click_cell=(196.5, 145),
                click_cell_drag_to=(194, 145),
                click_cell_drag_repeat_count=1,
                click_cell_drag_repeat_interval_sec=0.38,
                key="",
                delay_after_sec=0.45,
            ),
            HomePrepStep(key="1", delay_after_sec=0.12),
            HomePrepStep(key="enter", delay_after_sec=1.2),
            HomePrepStep(
                # Close storage
                click_cell=(201, 137),
                key="",
                delay_after_sec=1.0,
            ),
            HomePrepStep(
                # Close inventory
                key="e",
                hold_modifiers=("alt",),
                delay_after_sec=1.5,
            ),
            HomePrepStep(
                key="space",
                dismiss_chat_probe_client=_COMODO_SPACE_AFTER_INV_PROBE,
                dismiss_chat_min_channel=228,
                dismiss_chat_key="esc",
                delay_after_sec=0.55,
            ),
            HomePrepStep(
                # Walk: ground click on map cell (tune delay if path is long).
                click_cell=(217, 152),
                key="",
                delay_after_sec=5.0,
            ),
            HomePrepStep(
                click_cell=(225, 164),
                key="",
                delay_after_sec=1.0,
            ),
            HomePrepStep(
                click_cell=(218.5, 147.5),
                key="",
                delay_after_sec=1.0,
            ),
            HomePrepStep(
                # Buy Fresh Fish
                click_cell=(200, 158.2),
                click_cell_drag_to=(207, 156),
                click_cell_drag_repeat_count=1,
                click_cell_drag_repeat_interval_sec=0.38,
                key="",
                delay_after_sec=0.45,
            ),
            HomePrepStep(key="3", delay_after_sec=0.12),
            HomePrepStep(key="0", delay_after_sec=0.12),
            HomePrepStep(key="0", delay_after_sec=0.12),
            HomePrepStep(key="enter", delay_after_sec=1.2),
            HomePrepStep(
                click_cell=(210, 154.7),
                key="",
                delay_after_sec=1.0,
            ),
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
