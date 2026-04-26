"""Driver loop for :class:`HuntController`.

Simple while-loop: drain hotkey edges, tick, sleep. Hotkeys are
abstracted as two optional callables so the runner can wire them to
whatever source is convenient (Win32 ``GetAsyncKeyState``, tests, etc.).
"""

from __future__ import annotations

import time
from collections.abc import Callable

from ro_bot.hunt.controller import HuntController


def run_hunt_loop(
    controller: HuntController,
    should_stop: Callable[[], bool],
    toggle_pause: Callable[[], bool] | None = None,
) -> None:
    """Drive ``controller.tick()`` until ``should_stop()`` returns True.

    ``toggle_pause`` is polled each iteration; each True return flips
    the controller between paused and running. The loop keeps spinning
    while paused so the toggle stays responsive. On exit any pause is
    lifted so the controller is reusable.
    """
    controller.install()
    try:
        while not should_stop():
            if toggle_pause is not None and toggle_pause():
                if controller.is_paused():
                    controller.resume()
                else:
                    controller.pause()
            controller.tick()
            time.sleep(controller.tick_interval_sec())
    finally:
        if controller.is_paused():
            controller.resume()
        controller.uninstall()
