"""Absolute-HP heal policy.

Heals whenever current HP drops below ``HealConfig.min_hp``. The
sniffer's ``hp_max`` (from ``SP_MAXHP``) is shown in diagnostic logs
when available but does not influence the heal decision.

HP is sourced from the sniffer's 0x00B0 / 0x0ACB cache, which is
authoritative on the server side. The memory ``-0x2C50`` slot is
unreliable (multiplexed with target HP) — see
``docs/memory-offsets.md``.

``min_hp = 0`` disables the policy entirely (heal key never fires).
"""

from __future__ import annotations

import logging
import time

from ro_bot.core.hid.bridge import HidBridge
from ro_bot.core.network.sniffer import PacketSniffer
from ro_bot.hunt.config import HealConfig
from ro_bot.hunt.constants import HP_SNAPSHOT_INTERVAL_SEC

logger = logging.getLogger("ro_bot.hunt")


class HealPolicy:
    """Fire heal key when HP drops below ``min_hp``; log what it sees."""

    def __init__(
        self,
        cfg: HealConfig,
        bridge: HidBridge,
        sniffer: PacketSniffer,
        manual_control_maps: frozenset[str],
        *,
        all_maps: bool = False,
    ) -> None:
        self._cfg = cfg
        self._bridge = bridge
        self._sniffer = sniffer
        self._manual_control_maps = manual_control_maps
        self._all_maps = all_maps
        self._last_heal_at: float = 0.0
        self._last_snapshot_at: float = 0.0

    def tick(self, now: float) -> None:
        """One policy iteration. Call every controller tick."""
        self._log_snapshot(now)
        self._maybe_heal(now)

    def _log_snapshot(self, now: float) -> None:
        """Periodic INFO line showing what the policy currently sees."""
        if now - self._last_snapshot_at < HP_SNAPSHOT_INTERVAL_SEC:
            return
        self._last_snapshot_at = now

        hp, hp_max = self._sniffer.get_player_hp()
        map_name = self._sniffer.get_map_name() or "?"
        ok = self._consumables_ok()
        hp_max_str = str(hp_max) if hp_max > 0 else "?"
        reason = self._skip_reason(hp, ok)

        logger.info(
            "HP snapshot: hp=%d/%s map=%s consumables_ok=%s → %s",
            hp, hp_max_str, map_name, ok, reason,
        )

    def _skip_reason(self, hp: int, consumables_ok: bool) -> str:
        if self._cfg.min_hp <= 0:
            return "skip: min_hp=0 (heal disabled)"
        if hp <= 0:
            return "skip: hp<=0 (dead/stale)"
        if not consumables_ok:
            return "skip: manual_control_map (automation disabled)"
        if hp >= self._cfg.min_hp:
            return f"skip: above_min_hp (>={self._cfg.min_hp})"
        return f"would_heal (<{self._cfg.min_hp})"

    def _maybe_heal(self, now: float) -> None:
        if self._cfg.min_hp <= 0:
            return
        hp, hp_max = self._sniffer.get_player_hp()
        if hp <= 0 or hp >= self._cfg.min_hp:
            return
        if now - self._last_heal_at < self._cfg.cooldown_sec:
            return
        if not self._consumables_ok():
            return
        try:
            self._bridge.press_key(self._cfg.key)
        except Exception:
            logger.exception(
                "HID press_key('%s') failed (heal)", self._cfg.key,
            )
            return
        self._last_heal_at = now
        hp_max_str = str(hp_max) if hp_max > 0 else "?"
        logger.warning(
            "Heal: pressed '%s' (HP=%d/%s, threshold=%d)",
            self._cfg.key, hp, hp_max_str, self._cfg.min_hp,
        )

    def _consumables_ok(self) -> bool:
        name = self._sniffer.get_map_name()
        if name is None:
            return False
        if self._all_maps:
            return True
        return name not in self._manual_control_maps

    def shift(self, delta: float) -> None:
        """Pause/resume: slide all timestamps by ``delta``."""
        if self._last_heal_at:
            self._last_heal_at += delta
        if self._last_snapshot_at:
            self._last_snapshot_at += delta


def initial_time() -> float:
    """Kept for symmetry with other policies; equivalent to time.monotonic()."""
    return time.monotonic()
