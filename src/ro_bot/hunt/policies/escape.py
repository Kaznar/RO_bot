"""Dangerous-mob escape policy.

If the sniffer sees any mob whose name is in the ``dangerous_names``
set, the policy fires the configured teleport key and tells the
controller to abort the current target. Rate-limited by
``cooldown_sec`` so a failed teleport (no SP / silenced) doesn't
become a press storm while the dangerous mob remains in view.

The source of truth for "is a dangerous mob in view" is the sniffer
(which knows the moment the 0x0A30 spawn packet arrives). Using the
tracker would give up to ~1 s of free hits before the scanner resolves
the GID's memory address.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from ro_bot.core.hid.bridge import HidBridge
from ro_bot.core.network.sniffer import PacketSniffer
from ro_bot.hunt.config import EscapeConfig

logger = logging.getLogger("ro_bot.hunt")


class EscapePolicy:
    """Check for dangerous mobs each tick; press teleport when found."""

    def __init__(
        self,
        cfg: EscapeConfig,
        dangerous_names: frozenset[str],
        bridge: HidBridge,
        sniffer: PacketSniffer,
        *,
        on_teleport: Callable[[float], None] | None = None,
    ) -> None:
        self._cfg = cfg
        self._dangerous = dangerous_names
        self._bridge = bridge
        self._sniffer = sniffer
        self._on_teleport = on_teleport
        self._last_at: float = 0.0

    def has_danger(self) -> list[tuple[int, str]]:
        """Return currently-visible dangerous (gid, name) pairs."""
        if not self._dangerous:
            return []
        return [
            (e.gid, e.name)
            for e in self._sniffer.get_all_entities()
            if e.name in self._dangerous
        ]

    def press_if_ready(self, now: float) -> bool:
        """Fire the teleport key if the cooldown has elapsed.

        Returns True if the caller should skip the rest of the tick
        (dangerous mob in view; engagement was/ must be cancelled).
        Returns False when no danger is present.
        """
        threats = self.has_danger()
        if not threats:
            return False
        if now - self._last_at < self._cfg.cooldown_sec:
            return True
        try:
            self._bridge.press_key(self._cfg.key)
        except Exception:
            logger.exception(
                "HID press_key('%s') failed (escape)", self._cfg.key,
            )
            return True
        self._last_at = now
        logger.warning(
            "Escape: pressed '%s' (threats=%s)",
            self._cfg.key,
            ", ".join(f"{n} gid={g}" for g, n in threats),
        )
        if self._on_teleport is not None:
            self._on_teleport(now)
        return True

    def shift(self, delta: float) -> None:
        if self._last_at:
            self._last_at += delta
