"""Watchdog for silent hunt-automation stalls.

The tick loop can keep running (heal / weight snapshots) while the
hunt path never reaches candidate selection or idle teleport — for
example when memory player coordinates are temporarily unavailable.
This guard tracks the last meaningful automation step and forces a
recovery teleport when silence exceeds a derived limit.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from ro_bot.hunt.config import HuntConfig
from ro_bot.hunt.constants import AUTOMATION_STALL_SLACK_SEC
from ro_bot.hunt.policies.idle_action import IdleActionPolicy

logger = logging.getLogger("ro_bot.hunt")


def automation_stall_limit_sec(cfg: HuntConfig) -> float:
    """Upper bound on hunt silence before the watchdog fires."""
    idle_after = cfg.idle_action.after_sec if cfg.idle_action is not None else 10.0
    return (
        cfg.engagement.kill_timeout_sec
        + idle_after * 2.0
        + AUTOMATION_STALL_SLACK_SEC
    )


class AutomationStallGuard:
    """Monotonic-clock silence detector for active hunt automation."""

    def __init__(self, limit_sec: float) -> None:
        self.limit_sec = limit_sec
        self._last_progress_at: float | None = None

    def mark_progress(self, now: float) -> None:
        self._last_progress_at = now

    def reset(self, now: float) -> None:
        self._last_progress_at = now

    def shift(self, delta: float) -> None:
        if self._last_progress_at is not None:
            self._last_progress_at += delta

    def stalled_for(self, now: float) -> float:
        if self._last_progress_at is None:
            self._last_progress_at = now
            return 0.0
        return max(0.0, now - self._last_progress_at)

    def is_stalled(self, now: float) -> bool:
        return self.stalled_for(now) >= self.limit_sec


def recover_automation_stall(
    *,
    now: float,
    guard: AutomationStallGuard,
    idle: IdleActionPolicy | None,
    clear_engagement: Callable[[], None],
) -> bool:
    """Force recovery when hunt automation has been silent too long."""
    if not guard.is_stalled(now):
        return False

    stalled = guard.stalled_for(now)
    clear_engagement()
    if idle is not None:
        idle.force_fire(now, f"automation stall watchdog ({stalled:.1f}s)")
    else:
        logger.error(
            "Hunt automation stalled for %.1fs but idle_action is not configured",
            stalled,
        )
    logger.warning(
        "Hunt automation stall recovered after %.1fs (limit %.1fs)",
        stalled,
        guard.limit_sec,
    )
    guard.mark_progress(now)
    return True
