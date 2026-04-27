"""HP-threshold heal policy.

Two thresholds, primary + fallback:

* Primary: percentage of ``hp_max`` (``threshold_pct``). Used whenever
  the sniffer has observed ``SP_MAXHP``.
* Fallback: absolute HP floor (``min_hp``). Used only when ``hp_max``
  is unknown (some private servers / Gepard builds never emit
  ``SP_MAXHP=6``); set ``min_hp = 0`` to disable healing in that case.

HP is sourced from the sniffer's 0x00B0 / 0x0ACB cache, which is
authoritative on the server side. The memory `-0x2C50` slot is
unreliable (multiplexed with target HP) — see
``docs/memory-offsets.md``.
"""

from __future__ import annotations

import logging
import time

from ro_bot.core.hid.bridge import HidBridge
from ro_bot.core.network.sniffer import PacketSniffer
from ro_bot.hunt.config import HealConfig
from ro_bot.hunt.constants import (
    EMPTY_HP_CACHE_WARN_INTERVAL_SEC,
    HP_SNAPSHOT_INTERVAL_SEC,
)

logger = logging.getLogger("ro_bot.hunt")


class HealPolicy:
    """Fire heal key when HP drops below threshold; log what it sees."""

    def __init__(
        self,
        cfg: HealConfig,
        bridge: HidBridge,
        sniffer: PacketSniffer,
        allowed_maps: frozenset[str],
    ) -> None:
        self._cfg = cfg
        self._bridge = bridge
        self._sniffer = sniffer
        self._allowed_maps = allowed_maps
        self._last_heal_at: float = 0.0
        self._last_snapshot_at: float = 0.0
        self._last_empty_warn_at: float = 0.0

    def tick(self, now: float) -> None:
        """One policy iteration. Call every controller tick."""
        self._log_snapshot(now)
        self._maybe_heal(now)

    def _log_snapshot(self, now: float) -> None:
        """Periodic INFO line showing what the policy currently sees."""
        hp, hp_max = self._sniffer.get_player_hp()
        max_unknown = hp_max <= 0

        if max_unknown and self._cfg.min_hp <= 0 and (
            now - self._last_empty_warn_at >= EMPTY_HP_CACHE_WARN_INTERVAL_SEC
        ):
            sp_types = sorted(self._sniffer.get_sp_types_seen())
            logger.warning(
                "Heal disabled: hp_max=0 and min_hp=0 (no fallback). "
                "sp_types_seen=%s; heal will not fire",
                sp_types,
            )
            self._last_empty_warn_at = now

        if now - self._last_snapshot_at < HP_SNAPSHOT_INTERVAL_SEC:
            return
        self._last_snapshot_at = now

        map_name = self._sniffer.get_map_name() or "?"
        allowed = self._on_allowed_map()

        if max_unknown:
            self._log_fallback_snapshot(hp, map_name, allowed)
            return

        ratio_pct = 100.0 * hp / hp_max
        threshold_pct = self._cfg.threshold_pct * 100.0
        reason = self._skip_reason_pct(hp, hp_max, allowed, threshold_pct)
        logger.info(
            "HP snapshot: hp=%d/%d (%.1f%%) map=%s allowed=%s → %s",
            hp, hp_max, ratio_pct, map_name, allowed, reason,
        )

    def _log_fallback_snapshot(
        self, hp: int, map_name: str, allowed: bool,
    ) -> None:
        """Snapshot line when hp_max is unknown (absolute fallback mode)."""
        sp_types = sorted(self._sniffer.get_sp_types_seen())
        if hp <= 0:
            logger.info(
                "HP snapshot: hp=0/0 (cache empty) map=%s allowed=%s "
                "sp_types=%s → skip",
                map_name, allowed, sp_types,
            )
            return
        reason = self._skip_reason_abs(hp, allowed)
        logger.info(
            "HP snapshot: hp=%d/? (max unknown, fallback min_hp=%d) "
            "map=%s allowed=%s sp_types=%s → %s",
            hp, self._cfg.min_hp, map_name, allowed, sp_types, reason,
        )

    def _skip_reason_pct(
        self, hp: int, hp_max: int, allowed: bool, threshold_pct: float,
    ) -> str:
        if hp <= 0:
            return "skip: hp<=0 (dead/stale)"
        if not allowed:
            return "skip: map_not_allowed"
        if hp / hp_max >= self._cfg.threshold_pct:
            return f"skip: above_threshold (>={threshold_pct:.0f}%)"
        return f"would_heal (<{threshold_pct:.0f}%)"

    def _skip_reason_abs(self, hp: int, allowed: bool) -> str:
        if self._cfg.min_hp <= 0:
            return "skip: min_hp=0 (fallback disabled)"
        if not allowed:
            return "skip: map_not_allowed"
        if hp >= self._cfg.min_hp:
            return f"skip: above_min_hp (>={self._cfg.min_hp})"
        return f"would_heal (<{self._cfg.min_hp})"

    def _maybe_heal(self, now: float) -> None:
        hp, hp_max = self._sniffer.get_player_hp()
        if hp <= 0:
            return
        if hp_max > 0:
            if hp / hp_max >= self._cfg.threshold_pct:
                return
        else:
            if self._cfg.min_hp <= 0 or hp >= self._cfg.min_hp:
                return
        if now - self._last_heal_at < self._cfg.cooldown_sec:
            return
        if not self._on_allowed_map():
            return
        try:
            self._bridge.press_key(self._cfg.key)
        except Exception:
            logger.exception(
                "HID press_key('%s') failed (heal)", self._cfg.key,
            )
            return
        self._last_heal_at = now
        if hp_max > 0:
            logger.warning(
                "Heal: pressed '%s' (HP=%d/%d, %.1f%% < %.0f%%)",
                self._cfg.key, hp, hp_max,
                100.0 * hp / hp_max,
                100.0 * self._cfg.threshold_pct,
            )
        else:
            logger.warning(
                "Heal: pressed '%s' (HP=%d/?, fallback min_hp=%d)",
                self._cfg.key, hp, self._cfg.min_hp,
            )

    def _on_allowed_map(self) -> bool:
        name = self._sniffer.get_map_name()
        if name is None:
            return False
        return name in self._allowed_maps

    def shift(self, delta: float) -> None:
        """Pause/resume: slide all timestamps by ``delta``."""
        if self._last_heal_at:
            self._last_heal_at += delta
        if self._last_snapshot_at:
            self._last_snapshot_at += delta
        if self._last_empty_warn_at:
            self._last_empty_warn_at += delta


def initial_time() -> float:
    """Kept for symmetry with other policies; equivalent to time.monotonic()."""
    return time.monotonic()
