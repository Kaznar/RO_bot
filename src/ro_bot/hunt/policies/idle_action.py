"""Idle-timeout teleport policy.

Presses the configured key when there have been no whitelist
candidates visible for ``after_sec`` seconds. Immediately after a
confirmed kill a shorter ``after_kill_sec`` grace applies (the kill
itself spent 10+ s looking around, so waiting a full 10 s more is
wasteful if nothing showed up).

Resets on:

  * engage — we found something, timer irrelevant
  * engagement timeout — failed engage is not a fresh kill
  * map change — new map, new grace cycle

Caller decides *whether* to tick this policy based on the candidate
pool — see ``HuntController.tick``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from ro_bot.core.hid.bridge import HidBridge
from ro_bot.hunt.config import IdleActionConfig

logger = logging.getLogger("ro_bot.hunt")


class IdleActionPolicy:
    """Fires a single key when no candidates appear within the idle window."""

    def __init__(
        self,
        cfg: IdleActionConfig,
        bridge: HidBridge,
        *,
        on_teleport: Callable[[float], None] | None = None,
    ) -> None:
        self._cfg = cfg
        self._bridge = bridge
        self._on_teleport = on_teleport
        self._idle_since: float | None = None
        self._post_kill_grace: bool = False

    # ── Events from the controller ──────────────────────────────────

    def on_engaged(self) -> None:
        """Called when the controller engages a new target."""
        self._idle_since = None
        self._post_kill_grace = False

    def on_kill(self) -> None:
        """Called after a confirmed kill (vanish type=DIED)."""
        self._post_kill_grace = True

    def on_timeout(self) -> None:
        """Called when an engagement times out (not a real kill)."""
        self._post_kill_grace = False

    def on_map_reset(self) -> None:
        self._idle_since = None
        self._post_kill_grace = False

    def on_visible_trackable_name(self) -> None:
        """Sniffer still lists a whitelisted mob — defer idle teleport."""
        self._idle_since = None
        self._post_kill_grace = False

    # ── Tick ────────────────────────────────────────────────────────

    def tick(self, now: float) -> bool:
        """Advance the timer; fire the key when interval has elapsed."""
        if self._idle_since is None:
            self._idle_since = now
            return False
        interval = (
            self._cfg.after_kill_sec
            if self._post_kill_grace
            else self._cfg.after_sec
        )
        if now - self._idle_since < interval:
            return False
        elapsed = now - self._idle_since
        suffix = " (post-kill grace)" if self._post_kill_grace else ""
        return self._fire(now, f"after {elapsed:.1f}s without candidates{suffix}")

    def force_fire(self, now: float, reason: str) -> bool:
        """Fire the key immediately, bypassing ``after_sec``.

        Used by recovery flows (e.g. path-stuck) that already know
        there is nothing reachable here and shouldn't pay the regular
        idle grace.
        """
        return self._fire(now, reason)

    def _fire(self, now: float, reason: str) -> bool:
        try:
            self._bridge.press_key(self._cfg.key)
        except Exception:
            logger.exception(
                "HID press_key('%s') failed (idle)", self._cfg.key,
            )
            return False
        logger.info(
            "Idle action: pressed '%s' %s", self._cfg.key, reason,
        )
        self._idle_since = now
        self._post_kill_grace = False
        if self._on_teleport is not None:
            self._on_teleport(now)
        return True

    def shift(self, delta: float) -> None:
        if self._idle_since is not None:
            self._idle_since += delta
