"""Absolute-HP heal policy (item + skill channels).

Each :class:`~ro_bot.hunt.config.HealChannelConfig` heals when HP is below
its own ``min_hp``. HP comes from the sniffer 0x00B0 / 0x0ACB cache.
"""

from __future__ import annotations

import logging
import time
from typing import Literal

from ro_bot.core.hid.bridge import HidBridge
from ro_bot.core.network.sniffer import PacketSniffer
from ro_bot.hunt.aim_service import AimService
from ro_bot.hunt.config import GoHomeConfig, HealChannelConfig, HealConfig
from ro_bot.hunt.policies.go_home import execute_go_home, go_home_configured
from ro_bot.hunt.constants import HP_SNAPSHOT_INTERVAL_SEC

logger = logging.getLogger("ro_bot.hunt")

HealChannelName = Literal["item", "skill"]

SAVE_MODE_KEY = "t"
SAVE_MODE_RATIO = 0.5
SAVE_MODE_COOLDOWN_SEC = 180.0


class HealPolicy:
    """Fire heal keys per channel when HP drops below each channel's ``min_hp``."""

    def __init__(
        self,
        cfg: HealConfig,
        bridge: HidBridge,
        sniffer: PacketSniffer,
        manual_control_maps: frozenset[str],
        *,
        aim: AimService | None = None,
        all_maps: bool = False,
        go_home: GoHomeConfig | None = None,
        game_hwnd: int | None = None,
    ) -> None:
        self._cfg = cfg
        self._bridge = bridge
        self._go_home = go_home
        self._game_hwnd = game_hwnd
        self._sniffer = sniffer
        self._aim = aim
        self._manual_control_maps = manual_control_maps
        self._all_maps = all_maps
        self._channels = _build_channel_list(cfg)
        for name, ch in self._channels:
            if ch.click_self and aim is None:
                logger.error(
                    "Heal %s click_self=true requires AimService — key-only",
                    name,
                )
        self._last_heal_at: dict[HealChannelName, float] = {}
        self._last_save_tp_at: float = 0.0
        self._last_snapshot_at: float = 0.0
        self._save_recovery_deadline: float | None = None

    def tick(self, now: float) -> None:
        self._log_snapshot(now)
        if self._maybe_save_teleport(now):
            return
        if self._maybe_finalize_save_recovery(now):
            return
        self._maybe_heal(now)

    def _log_snapshot(self, now: float) -> None:
        if now - self._last_snapshot_at < HP_SNAPSHOT_INTERVAL_SEC:
            return
        self._last_snapshot_at = now

        hp, hp_max = self._sniffer.get_player_hp()
        map_name = self._sniffer.get_map_name() or "?"
        ok = self._consumables_ok()
        hp_max_str = str(hp_max) if hp_max > 0 else "?"
        parts = [
            f"{name}:{self._skip_reason(hp, ok, ch)}"
            for name, ch in self._channels
        ]
        if not parts:
            parts.append(self._skip_reason(hp, ok, None))

        logger.info(
            "HP snapshot: hp=%d/%s map=%s consumables_ok=%s → %s",
            hp, hp_max_str, map_name, ok, "; ".join(parts),
        )

    def _skip_reason(
        self,
        hp: int,
        consumables_ok: bool,
        ch: HealChannelConfig | None,
    ) -> str:
        if ch is None:
            return "skip: no heal channels"
        if ch.min_hp <= 0:
            return "skip: min_hp=0 (disabled)"
        if hp <= 0:
            return "skip: hp<=0 (dead/stale)"
        if not consumables_ok:
            return "skip: manual_control_map"
        if hp >= ch.min_hp:
            return f"skip: above_min_hp (>={ch.min_hp})"
        return f"would_heal (<{ch.min_hp})"

    def _maybe_heal(self, now: float) -> None:
        if not self._channels:
            return
        hp, hp_max = self._sniffer.get_player_hp()
        if hp <= 0:
            return
        if not self._consumables_ok():
            return
        for name, ch in self._channels:
            if hp >= ch.min_hp:
                continue
            last = self._last_heal_at.get(name, 0.0)
            if now - last < ch.cooldown_sec:
                continue
            if self._cast_heal(name, ch, hp, hp_max):
                self._last_heal_at[name] = now

    def _press_heal_keys(self, ch: HealChannelConfig) -> bool:
        keys = ch.keys
        if not keys:
            return False
        gap = max(0.0, ch.key_interval_sec)
        for i, key in enumerate(keys):
            try:
                self._bridge.press_key(key)
            except Exception:
                logger.exception("HID press_key('%s') failed (heal)", key)
                return False
            if gap > 0 and i < len(keys) - 1:
                time.sleep(gap)
        return True

    def _cast_heal(
        self,
        name: HealChannelName,
        ch: HealChannelConfig,
        hp: int,
        hp_max: int,
    ) -> bool:
        keys = ch.keys
        if not keys:
            return False
        if ch.click_self and self._aim is not None:
            px, py = self._sniffer.get_player_pos()
            if px <= 0 and py <= 0:
                logger.debug(
                    "Heal %s: no player position yet — skip skill click", name,
                )
                return False
            player_cell = (px, py)
            if not self._press_heal_keys(ch):
                return False
            delay = max(0.0, ch.skill_delay_sec)
            if delay > 0:
                time.sleep(delay)
            if not self._aim.aim_and_click(
                player_cell, player_cell, target_name=None,
            ):
                logger.warning(
                    "Heal %s: keys %s ok but self click failed (dead zone?)",
                    name, keys,
                )
                return False
        elif not self._press_heal_keys(ch):
            return False
        hp_max_str = str(hp_max) if hp_max > 0 else "?"
        mode = "skill+click" if ch.click_self else "key"
        keys_label = "+".join(keys)
        logger.warning(
            "Heal %s: %s %s (HP=%d/%s, threshold=%d)",
            name, mode, keys_label, hp, hp_max_str, ch.min_hp,
        )
        return True

    def _min_active_hp(self) -> int:
        thresholds = [ch.min_hp for _, ch in self._channels if ch.min_hp > 0]
        return min(thresholds) if thresholds else 0

    def _maybe_save_teleport(self, now: float) -> bool:
        min_hp = self._min_active_hp()
        if min_hp <= 0:
            return False
        hp, hp_max = self._sniffer.get_player_hp()
        if hp <= 0:
            return False
        if not self._consumables_ok():
            return False
        critical_hp = int(min_hp * SAVE_MODE_RATIO)
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
                min_hp, check_sec, self._cfg.save_recovery_key,
            )
        return True

    def _maybe_finalize_save_recovery(self, now: float) -> bool:
        deadline = self._save_recovery_deadline
        if deadline is None or now < deadline:
            return False
        self._save_recovery_deadline = None
        min_hp = self._min_active_hp()
        if self._cfg.save_recovery_check_sec <= 0 or min_hp <= 0:
            return False
        if not self._consumables_ok():
            return False
        hp, hp_max = self._sniffer.get_player_hp()
        if hp <= 0:
            return False
        hp_max_str = str(hp_max) if hp_max > 0 else "?"
        if hp >= min_hp:
            logger.info(
                "Save mode: HP recovered to %d/%s (>= %d) after save teleport",
                hp, hp_max_str, min_hp,
            )
            return False
        if not go_home_configured(self._go_home):
            fallback = (self._cfg.save_recovery_key or "").strip()
            if not fallback:
                logger.warning(
                    "Save mode: HP still %d/%s (<%d) after %.1fs but "
                    "save_recovery_key is empty",
                    hp, hp_max_str, min_hp, self._cfg.save_recovery_check_sec,
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
                fallback, hp, hp_max_str, min_hp,
                self._cfg.save_recovery_check_sec,
            )
            return True
        try:
            assert self._go_home is not None
            execute_go_home(self._bridge, self._go_home, game_hwnd=self._game_hwnd)
        except Exception:
            logger.exception("Go home failed (save recovery)")
            return False
        logger.warning(
            "Save mode: go home (HP=%d/%s still <%d after %.1fs)",
            hp, hp_max_str, min_hp, self._cfg.save_recovery_check_sec,
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
        for name in list(self._last_heal_at):
            self._last_heal_at[name] += delta
        if self._last_save_tp_at:
            self._last_save_tp_at += delta
        if self._last_snapshot_at:
            self._last_snapshot_at += delta
        if self._save_recovery_deadline is not None:
            self._save_recovery_deadline += delta


def _build_channel_list(
    cfg: HealConfig,
) -> list[tuple[HealChannelName, HealChannelConfig]]:
    out: list[tuple[HealChannelName, HealChannelConfig]] = []
    if cfg.item is not None and cfg.item.min_hp > 0 and cfg.item.keys:
        out.append(("item", cfg.item))
    if cfg.skill is not None and cfg.skill.min_hp > 0 and cfg.skill.keys:
        out.append(("skill", cfg.skill))
    out.sort(key=lambda pair: pair[1].min_hp, reverse=True)
    return out


def initial_time() -> float:
    return time.monotonic()
