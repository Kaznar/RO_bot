"""Global hotkey edge detection via Win32 ``GetAsyncKeyState``.

Global = the keys fire even when the game window owns focus. That's
what we want — the operator shouldn't have to alt-tab to pause or quit
the bot.

Function keys are used so operator controls stay outside the RO action
bar / movement zone. See `VirtualKey` below.
"""

from __future__ import annotations

import ctypes
from enum import IntEnum

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_GetAsyncKeyState = _user32.GetAsyncKeyState
_GetAsyncKeyState.argtypes = [ctypes.c_int]
_GetAsyncKeyState.restype = ctypes.c_short


class VirtualKey(IntEnum):
    """Win32 VK_ codes for the hotkeys we actually use."""
    F1 = 0x70  # pause / resume
    F9 = 0x78  # quit


class HotkeyWatcher:
    """Edge-detects Win32 virtual keys across ticks.

    `pressed(vk)` returns True exactly once per press-down. Internal
    state tracks last-known `down` state so a held key doesn't register
    as a stream of presses.
    """

    def __init__(self) -> None:
        self._state: dict[int, bool] = {}

    def pressed(self, vk: int) -> bool:
        """True on the first tick after `vk` transitions from up → down."""
        down = (_GetAsyncKeyState(int(vk)) & 0x8000) != 0
        was_down = self._state.get(vk, False)
        self._state[vk] = down
        return down and not was_down
