"""Pause / resume support — centralized time-shift accounting.

The hunt controller holds many monotonic-clock timestamps (engagement
start, last click, last heal, buff timers, cell settles, blacklist
expiries). When the operator pauses the bot, those timestamps become
stale — resuming 30 s later shouldn't trigger a ``kill_timeout`` or
fire every buff at once.

``PauseToken`` captures the pause instant; on resume it returns the
elapsed duration so every registered timestamp can be shifted forward
by that amount.
"""

from __future__ import annotations

import time
from collections.abc import Callable


class PauseToken:
    """Single pause/resume pair.

    Usage::

        token = PauseToken()
        token.pause()
        ...
        if token.is_paused:
            return
        ...
        delta = token.resume()  # returns seconds paused
        # now shift every timestamp by `delta`
    """

    def __init__(self) -> None:
        self._paused_at: float | None = None

    @property
    def is_paused(self) -> bool:
        return self._paused_at is not None

    def pause(self) -> None:
        if self._paused_at is None:
            self._paused_at = time.monotonic()

    def resume(self) -> float:
        """Return elapsed pause duration in seconds (0 if not paused)."""
        if self._paused_at is None:
            return 0.0
        delta = time.monotonic() - self._paused_at
        self._paused_at = None
        return delta


def shift_scalar(value: float, delta: float) -> float:
    """Shift a monotonic timestamp forward by ``delta`` (0 stays 0)."""
    return value + delta if value else value


def apply_shift(fn: Callable[[float], None], delta: float) -> None:
    """Call ``fn(delta)`` only if delta is non-zero."""
    if delta:
        fn(delta)
