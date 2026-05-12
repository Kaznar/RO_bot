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

# Emergency self-save teleport when HP drops under 50% of configured
# heal threshold. Kept intentionally fixed per user requirement.
SAVE_MODE_KEY = "t"
SAVE_MODE_RATIO = 0.5
SAVE_MODE_COOLDOWN_SEC = 180.0


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
        self._last_save_tp_at: float = 0.0
        self._last_snapshot_at: float = 0.0
        self._save_recovery_deadline: float | None = None

    def tick(self, now: float) -> None:
        """One policy iteration. Call every controller tick."""
        self._log_snapshot(now)
        if self._maybe_save_teleport(now):
            return
        if self._maybe_finalize_save_recovery(now):
            return
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

    def _maybe_save_teleport(self, now: float) -> bool:
        """Emergency teleport when HP is critically low.

        Trigger condition: ``hp < min_hp * 0.5``.
        Cooldown is independent from heal cooldown so repeated low-HP
        periods cannot spam teleport key presses.
        """
        if self._cfg.min_hp <= 0:
            return False
        hp, hp_max = self._sniffer.get_player_hp()
        if hp <= 0:
            return False
        if not self._consumables_ok():
            return False
        critical_hp = int(self._cfg.min_hp * SAVE_MODE_RATIO)
        if hp >= critical_hp:
            return False
        if now - self._last_save_tp_at < SAVE_MODE_COOLDOWN_SEC:
            return False
        try:
            self._bridge.press_key(SAVE_MODE_KEY)
        except Exception:
            logger.exception(
                "HID press_key('%s') failed (save mode)", SAVE_MODE_KEY,
            )
            return False
        self._last_save_tp_at = now
        check_sec = self._cfg.save_recovery_check_sec
        if check_sec > 0:
            self._save_recovery_deadline = now + check_sec
        hp_max_str = str(hp_max) if hp_max > 0 else "?"
        logger.warning(
            "Save mode: pressed '%s' (HP=%d/%s, trigger<%d, cooldown=%.0fs)",
            SAVE_MODE_KEY, hp, hp_max_str, critical_hp, SAVE_MODE_COOLDOWN_SEC,
        )
        if check_sec > 0:
            logger.info(
                "Save mode: will check HP vs %d in %.1fs (fallback key=%r)",
                self._cfg.min_hp, check_sec, self._cfg.save_recovery_key,
            )
        return True

    def _maybe_finalize_save_recovery(self, now: float) -> bool:
        """After save teleport, press fallback key if HP stayed below ``min_hp``."""
        deadline = self._save_recovery_deadline
        if deadline is None or now < deadline:
            return False
        self._save_recovery_deadline = None
        if self._cfg.save_recovery_check_sec <= 0:
            return False
        if self._cfg.min_hp <= 0:
            return False
        if not self._consumables_ok():
            return False
        hp, hp_max = self._sniffer.get_player_hp()
        if hp <= 0:
            return False
        hp_max_str = str(hp_max) if hp_max > 0 else "?"
        if hp >= self._cfg.min_hp:
            logger.info(
                "Save mode: HP recovered to %d/%s (>= %d) after save teleport",
                hp, hp_max_str, self._cfg.min_hp,
            )
            return False
        fallback = (self._cfg.save_recovery_key or "").strip()
        if not fallback:
            logger.warning(
                "Save mode: HP still %d/%s (<%d) after %.1fs but "
                "save_recovery_key is empty",
                hp, hp_max_str, self._cfg.min_hp,
                self._cfg.save_recovery_check_sec,
            )
            return False
        try:
            self._bridge.press_key(fallback)
        except Exception:
            logger.exception(
                "HID press_key('%s') failed (save recovery)", fallback,
            )
            return False
        logger.warning(
            "Save mode: pressed '%s' (HP=%d/%s still <%d after %.1fs)",
            fallback, hp, hp_max_str, self._cfg.min_hp,
            self._cfg.save_recovery_check_sec,
        )
        return True

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
        if self._last_save_tp_at:
            self._last_save_tp_at += delta
        if self._last_snapshot_at:
            self._last_snapshot_at += delta
        if self._save_recovery_deadline is not None:
            self._save_recovery_deadline += delta


def initial_time() -> float:
    """Kept for symmetry with other policies; equivalent to time.monotonic()."""
    return time.monotonic()
