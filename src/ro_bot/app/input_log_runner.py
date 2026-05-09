"""Low-level mouse / keyboard capture while the game window is focused.

Uses ``pynput`` global hooks. Events are logged only when the foreground
window title contains ``profile.server.window_title`` (case-insensitive).

Mouse **position** is read with the same Win32 APIs as :mod:`ro_bot.core.window`
(``GetCursorPos`` + optional client offset vs foreground ``HWND``). ``pynput``'s
``(x, y)`` callback args can disagree with that space on Windows (DPI / multi
monitor), so they are not used for coordinates.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

import win32gui
from pynput import keyboard, mouse

from ro_bot.app.prep_log_runner import wait_prep_until_in_world
from ro_bot.core.logging_setup import INPUT_CAPTURE_LOGGER_NAME
from ro_bot.core.memory.player_state import PlayerReader
from ro_bot.core.network.sniffer import PacketSniffer
from ro_bot.core.window import get_cursor_pos

CAP_LOG = logging.getLogger(INPUT_CAPTURE_LOGGER_NAME)
POLL_SEC = 0.05


def foreground_title_matches(substring: str) -> bool:
    if not substring.strip():
        return True
    hwnd = win32gui.GetForegroundWindow()
    title = win32gui.GetWindowText(hwnd)
    return substring.lower() in title.lower()


def _format_key(key: keyboard.Key | keyboard.KeyCode) -> str:
    if isinstance(key, keyboard.KeyCode):
        if key.char is not None:
            return f"char={key.char!r}"
        return f"vk={key.vk!r}"
    return f"name={key.name!r}"


def run_input_capture_loop(
    sniffer: PacketSniffer,
    player_reader: PlayerReader,
    *,
    window_title_substring: str,
    char_name: str,
    should_stop: Callable[[], bool],
    world_ready_timeout_sec: float,
    skip_in_world_wait: bool,
) -> int:
    """Log mouse clicks + keys while the game window is focused.

    Hooks start **before** the optional in-world wait so clicks during
    ``PREP_WAIT`` are still recorded (same title filter).
    """
    title = window_title_substring.strip() or "(any)"

    def on_click(_x: int, _y: int, button: mouse.Button, pressed: bool) -> None:
        if not pressed:
            return
        if should_stop():
            return
        if not foreground_title_matches(window_title_substring):
            return
        sx, sy = get_cursor_pos()
        client = ""
        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                cl, ct, cr, cb = win32gui.GetClientRect(hwnd)
                cw, ch = cr - cl, cb - ct
                org = win32gui.ClientToScreen(hwnd, (0, 0))
                cpx, cpy = sx - org[0], sy - org[1]
                if 0 <= cpx <= cw and 0 <= cpy <= ch:
                    client = f" client=({cpx},{cpy})"
        except Exception:
            pass
        CAP_LOG.info(
            "INPUT_MOUSE press button=%s screen=(%d,%d)%s",
            button,
            sx,
            sy,
            client,
        )

    def on_press(key: keyboard.Key | keyboard.KeyCode) -> None:
        if should_stop():
            return
        if not foreground_title_matches(window_title_substring):
            return
        CAP_LOG.info("INPUT_KEY press %s", _format_key(key))

    ml = mouse.Listener(on_click=on_click)
    kl = keyboard.Listener(on_press=on_press)
    ml.start()
    kl.start()
    try:
        CAP_LOG.info(
            "INPUT_CAPTURE_LISTENING filter_window_title=%r — "
            "klikaj ve hře (aktivní okno musí mít titulek s tímto řetězcem); "
            "``client=(x,y)`` jen uvnitř klientské oblasti. Čekání na svět…",
            title,
        )
        if not skip_in_world_wait:
            if not wait_prep_until_in_world(
                sniffer,
                player_reader,
                char_name=char_name,
                should_stop=should_stop,
                deadline_sec=world_ready_timeout_sec,
                status_log=CAP_LOG,
            ):
                return 1
        CAP_LOG.info(
            "INPUT_CAPTURE_BEGIN — svět OK; pokračuj v klikání, Numpad 0 ukončí.",
        )
        while not should_stop():
            time.sleep(POLL_SEC)
    finally:
        ml.stop()
        kl.stop()
        ml.join(timeout=2.5)
        kl.join(timeout=2.5)
        CAP_LOG.info("INPUT_CAPTURE_END")
    return 0
