"""Timed buff refresher.

Each ``BuffSpec`` has a key and an interval. The policy presses that
key once every ``interval_sec`` while consumables are allowed (map not
in ``manual_control_maps``, typically towns). Timers are anchored
to ``install()`` so the first press of each buff fires one full interval
later — assumption is that the operator self-buffed before launching.

Skipped on blocked maps; timestamps are not advanced during the skipped
window, so a buff that would have fired fires immediately on return.
"""

from __future__ import annotations

import logging
import time

from ro_bot.core.hid.bridge import HidBridge
from ro_bot.core.network.sniffer import PacketSniffer
from ro_bot.hunt.config import BuffSpec

logger = logging.getLogger("ro_bot.hunt")


class BuffPolicy:
    """Per-key interval presser."""

    def __init__(
        self,
        buffs: tuple[BuffSpec, ...],
        bridge: HidBridge,
        sniffer: PacketSniffer,
        manual_control_maps: frozenset[str],
        *,
        all_maps: bool = False,
    ) -> None:
        self._buffs = buffs
        self._bridge = bridge
        self._sniffer = sniffer
        self._manual_control_maps = manual_control_maps
        self._all_maps = all_maps
        self._last_at: dict[str, float] = {}

    def install(self) -> None:
        """Anchor every buff timer to "now" so the first press is one
        full interval away.
        """
        now = time.monotonic()
        self._last_at = {b.key: now for b in self._buffs}

    def uninstall(self) -> None:
        self._last_at.clear()

    def tick(self, now: float) -> None:
        if not self._last_at or not self._consumables_ok():
            return
        for buff in self._buffs:
            self._maybe_press(buff, now)

    def _maybe_press(self, buff: BuffSpec, now: float) -> None:
        last = self._last_at.get(buff.key)
        if last is None:
            return
        if now - last < buff.interval_sec:
            return
        try:
            self._bridge.press_key(buff.key)
        except Exception:
            logger.exception(
                "HID press_key('%s') failed (buff)", buff.key,
            )
            return
        self._last_at[buff.key] = now
        logger.info(
            "Buff: pressed '%s' (next in %.0fs)", buff.key, buff.interval_sec,
        )

    def _consumables_ok(self) -> bool:
        name = self._sniffer.get_map_name()
        if name is None:
            return False
        if self._all_maps:
            return True
        return name not in self._manual_control_maps

    def shift(self, delta: float) -> None:
        if not self._last_at:
            return
        self._last_at = {k: t + delta for k, t in self._last_at.items()}
