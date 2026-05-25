"""Critical-HP walk click toward a town warp (same outcome as manual ``h``).

When memory HP crosses from above ``hp_at_most`` down into ``(0, hp_at_most]``
(typically **1 HP** on the death screen) we issue ground walk clicks toward a
town warp. The same return sequence retries with ``town_return_escape_key``
until the character reaches a ``manual_control_maps`` town or HP recovers.

**HP == 0** from sniffer or memory is treated as stale / unknown during normal
play — it must never trigger death return on its own.

If the character stays on a hunt map, :meth:`tick` presses
``town_return_escape_key`` after ``town_return_retry_sec`` and repeats the walk
clicks (e.g. death dialog blocking the warp).

``delta_y_cells`` defaults negative so that ``player_y + delta`` moves toward
map south when ``+Y`` is north (common RO layout). Flip the sign if your client
is inverted.
"""

from __future__ import annotations

import logging
import time

from ro_bot.core.hid.bridge import HidBridge
from ro_bot.core.memory.player_state import PlayerState
from ro_bot.core.network.sniffer import PacketSniffer
from ro_bot.hunt.aim_service import AimService
from ro_bot.hunt.config import DeathReturnConfig

logger = logging.getLogger("ro_bot.hunt")


class DeathReturnPolicy:
    """One walk click per downward HP crossing into the critical band."""

    def __init__(
        self,
        cfg: DeathReturnConfig,
        bridge: HidBridge,
        aim: AimService,
        sniffer: PacketSniffer,
        manual_control_maps: frozenset[str],
        *,
        all_maps: bool = False,
    ) -> None:
        self._cfg = cfg
        self._bridge = bridge
        self._aim = aim
        self._sniffer = sniffer
        self._manual_control_maps = manual_control_maps
        self._all_maps = all_maps
        self._prev_hp: int | None = None
        #: After walk clicks, ignore further edges until town warp or retry.
        self._walk_click_latched: bool = False
        self._walk_clicked_at: float | None = None
        #: Number of retry cycles fired since the latest critical-HP edge.
        #: Reset on map change or when the sniffer reports HP recovered.
        self._retry_count: int = 0

    def on_map_reset(self) -> None:
        self._prev_hp = None
        self._clear_return_pending()

    def tick(
        self,
        current_map: str,
        st: PlayerState | None,
        now: float,
    ) -> bool:
        """Return True if the controller should stop the rest of this tick."""
        if not self._automation_ok(current_map):
            return False

        if self._walk_click_latched:
            if not self._all_maps and current_map in self._manual_control_maps:
                if self._retry_count > 0:
                    logger.warning(
                        "Death return: arrived on %s after %d retry cycle(s)",
                        current_map, self._retry_count,
                    )
                self._clear_return_pending()
                return False
            if self._sniffer_clears_pending(st):
                self._clear_return_pending()
                return False
            self._maybe_town_return_retry(now, current_map, st)
            return True

        if self._player_dead(st):
            if self._start_return_sequence(now, current_map, st, reason="dead"):
                return True
            if st is not None:
                self._prev_hp = st.hp
            return False

        if st is None or st.hp_max <= 0:
            self._prev_hp = None
            return False

        hp = st.hp
        prev = self._prev_hp
        n = self._cfg.hp_at_most
        if hp > n:
            self._prev_hp = hp
            return False

        if prev is None or prev <= n:
            self._prev_hp = hp
            return False

        if not self._sniffer_confirms_crit():
            hp_sn, hp_max_sn = self._sniffer.get_player_hp()
            logger.warning(
                "Death return: memory HP=%d crossed into band (prev=%d) but "
                "sniffer HP=%d/%d — proceeding on memory edge",
                hp, prev, hp_sn, hp_max_sn,
            )

        self._prev_hp = hp

        if self._start_return_sequence(now, current_map, st, reason="critical"):
            return True
        return False

    def _arm_return_pending(self, now: float) -> None:
        self._walk_click_latched = True
        self._walk_clicked_at = now

    def _clear_return_pending(self) -> None:
        self._walk_click_latched = False
        self._walk_clicked_at = None
        self._retry_count = 0

    def _maybe_town_return_retry(
        self,
        now: float,
        current_map: str,
        st: PlayerState | None,
    ) -> bool:
        retry_sec = self._cfg.town_return_retry_sec
        if retry_sec <= 0 or self._walk_clicked_at is None:
            return False
        if now - self._walk_clicked_at < retry_sec:
            return False

        if self._sniffer_clears_pending(st):
            self._clear_return_pending()
            return False

        if not self._all_maps and current_map in self._manual_control_maps:
            self._clear_return_pending()
            return False

        self._retry_count += 1
        escape = (self._cfg.town_return_escape_key or "").strip()
        if escape:
            try:
                self._bridge.press_key(escape)
            except Exception:
                logger.exception(
                    "Death return: press_key(%r) failed (town retry #%d)",
                    escape, self._retry_count,
                )
            else:
                logger.warning(
                    "Death return: retry #%d — pressed %r, still on %s, "
                    "redoing walk clicks",
                    self._retry_count, escape, current_map,
                )

        self._walk_clicked_at = now
        self._walk_click_latched = False

        # Always re-issue walk clicks on retry while we are still on a hunt
        # map: ``_sniffer_clears_pending`` above already exits early when
        # the sniffer reports HP recovered above the critical band, so a
        # fall-through here means we are still stuck (HP critical, HP=0
        # death screen, or sniffer/memory disagree). The previous click
        # cycle clearly did not warp us out, so press escape + walk-click
        # again, every ``town_return_retry_sec`` until we arrive in a
        # manual-control map or HP recovers.
        resolved = self._resolve_position(st)
        if resolved is None:
            self._arm_return_pending(now)
            return True
        px, py, hp, hp_max = resolved
        self._issue_walk_clicks(px, py, hp, hp_max, current_map, reason="retry")
        self._arm_return_pending(now)
        return True

    def _resolve_position(
        self,
        st: PlayerState | None,
    ) -> tuple[int, int, int, int] | None:
        if st is not None and st.hp_max > 0:
            px, py = st.x, st.y
            if px != 0 or py != 0:
                return px, py, st.hp, st.hp_max
        sx, sy = self._sniffer.get_player_pos()
        if sx == 0 and sy == 0:
            return None
        hp_sn, hp_max_sn = self._sniffer.get_player_hp()
        hp_max = hp_max_sn if hp_max_sn > 0 else 1
        return sx, sy, hp_sn, hp_max

    def _in_death_band(self, hp: int, hp_max: int) -> bool:
        """Death screen band — strictly ``0 < hp <= hp_at_most`` (not HP=0)."""
        return hp_max > 0 and 0 < hp <= self._cfg.hp_at_most

    def _player_dead(self, st: PlayerState | None) -> bool:
        hp_sn, hp_max_sn = self._sniffer.get_player_hp()
        sniff = self._in_death_band(hp_sn, hp_max_sn)
        mem = (
            st is not None
            and self._in_death_band(st.hp, st.hp_max)
        )
        if st is not None and st.hp_max > 0 and st.hp > self._cfg.hp_at_most:
            return False
        if hp_max_sn > 0 and hp_sn > self._cfg.hp_at_most:
            return False
        return sniff or mem

    def _start_return_sequence(
        self,
        now: float,
        current_map: str,
        st: PlayerState | None,
        *,
        reason: str,
    ) -> bool:
        resolved = self._resolve_position(st)
        if resolved is None:
            return False
        px, py, hp, hp_max = resolved
        if not self._issue_walk_clicks(
            px, py, hp, hp_max, current_map, reason=reason,
        ):
            return False
        self._arm_return_pending(now)
        return True

    def _sniffer_confirms_crit(self) -> bool:
        hp_sn, hp_max_sn = self._sniffer.get_player_hp()
        if hp_max_sn <= 0 or hp_sn <= 0:
            return False
        return hp_sn <= self._cfg.hp_at_most

    def _sniffer_clears_pending(self, st: PlayerState | None) -> bool:
        hp_sn, hp_max_sn = self._sniffer.get_player_hp()
        if hp_max_sn > 0 and hp_sn > self._cfg.hp_at_most:
            logger.info(
                "Death return: sniffer HP=%d/%d above band — aborting",
                hp_sn, hp_max_sn,
            )
            return True
        if st is not None and st.hp_max > 0 and st.hp > self._cfg.hp_at_most:
            logger.info(
                "Death return: memory HP=%d/%d above band — aborting",
                st.hp, st.hp_max,
            )
            return True
        return False

    def _issue_walk_clicks(
        self,
        px: int,
        py: int,
        hp: int,
        hp_max: int,
        current_map: str,
        *,
        reason: str = "critical",
    ) -> bool:
        target = (
            float(px) + self._cfg.delta_x_cells,
            float(py) + self._cfg.delta_y_cells,
        )
        try:
            self._aim.aim_and_click(
                (px, py),
                target,
                target_name=None,
                aim_settle_sec=self._cfg.aim_settle_sec,
            )
        except Exception:
            logger.exception("Death return: aim_and_click failed")
            return False

        sx = self._cfg.second_delta_x_cells
        sy = self._cfg.second_delta_y_cells
        if sx is not None and sy is not None:
            target2 = (target[0] + sx, target[1] + sy)
            delay = max(0.0, self._cfg.second_click_delay_sec)
            if delay > 0:
                time.sleep(delay)
            try:
                self._aim.aim_and_click(
                    (px, py),
                    target2,
                    target_name=None,
                    aim_settle_sec=self._cfg.aim_settle_sec,
                )
            except Exception:
                logger.exception("Death return: second aim_and_click failed")
                return True
            logger.warning(
                "Death return (%s): walk-click #1 (%.2f, %.2f) #2 (%.2f, %.2f) "
                "(player %d,%d HP=%d/%d map=%s)",
                reason,
                target[0],
                target[1],
                target2[0],
                target2[1],
                px,
                py,
                hp,
                hp_max,
                current_map,
            )
        else:
            logger.warning(
                "Death return (%s): walk-click toward (%.2f, %.2f) "
                "(player %d,%d HP=%d/%d map=%s — same town hand-off as manual h)",
                reason,
                target[0],
                target[1],
                px,
                py,
                hp,
                hp_max,
                current_map,
            )
        return True

    def _automation_ok(self, map_name: str) -> bool:
        if map_name == "?":
            return False
        if self._all_maps:
            return True
        return map_name not in self._manual_control_maps
