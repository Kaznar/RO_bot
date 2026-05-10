"""Critical-HP walk click toward a town warp (same outcome as manual ``h``).

When memory HP crosses from above ``hp_at_most`` down into ``(0, hp_at_most]``,
we issue one or two ground :meth:`~ro_bot.hunt.aim_service.AimService.aim_and_click`
calls: first at ``player + (delta_x_cells, delta_y_cells)``; when
``second_delta_*`` are both set, a second click at the first target plus those
offsets. After the client warps to a map
listed in ``manual_control_maps``, :class:`~ro_bot.hunt.controller.HuntController`
already suspends automation like after a butterfly-wing return.

``delta_y_cells`` defaults negative so that ``player_y + delta`` moves toward
map south when ``+Y`` is north (common RO layout). Flip the sign if your client
is inverted.
"""

from __future__ import annotations

import logging
import time

from ro_bot.core.memory.player_state import PlayerState
from ro_bot.hunt.aim_service import AimService
from ro_bot.hunt.config import DeathReturnConfig

logger = logging.getLogger("ro_bot.hunt")


class DeathReturnPolicy:
    """One walk click per downward HP crossing into the critical band."""

    def __init__(
        self,
        cfg: DeathReturnConfig,
        aim: AimService,
        manual_control_maps: frozenset[str],
        *,
        all_maps: bool = False,
    ) -> None:
        self._cfg = cfg
        self._aim = aim
        self._manual_control_maps = manual_control_maps
        self._all_maps = all_maps
        self._prev_hp: int | None = None
        #: After a successful first ground click, ignore further edges until
        #: :meth:`on_map_reset` (memory HP can briefly read above the band and
        #: would otherwise re-arm the edge on the same map).
        self._walk_click_latched: bool = False

    def on_map_reset(self) -> None:
        self._prev_hp = None
        self._walk_click_latched = False

    def tick(
        self,
        current_map: str,
        st: PlayerState | None,
    ) -> bool:
        """Return True if the controller should stop the rest of this tick."""
        if st is None or st.hp_max <= 0:
            self._prev_hp = None
            return False

        hp = st.hp
        prev = self._prev_hp
        self._prev_hp = hp

        if not self._automation_ok(current_map):
            return False

        n = self._cfg.hp_at_most
        if self._walk_click_latched:
            return False

        if hp <= 0 or hp > n:
            return False

        if prev is None or prev <= n:
            return False

        px, py = st.x, st.y
        if px == 0 and py == 0:
            return False

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
        self._walk_click_latched = True

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
                "Death return: walk-click #1 (%.2f, %.2f) #2 (%.2f, %.2f) "
                "(player %d,%d HP=%d/%d map=%s)",
                target[0],
                target[1],
                target2[0],
                target2[1],
                px,
                py,
                hp,
                st.hp_max,
                current_map,
            )
        else:
            logger.warning(
                "Death return: walk-click toward (%.2f, %.2f) "
                "(player %d,%d HP=%d/%d map=%s — same town hand-off as manual h)",
                target[0],
                target[1],
                px,
                py,
                hp,
                st.hp_max,
                current_map,
            )
        return True

    def _automation_ok(self, map_name: str) -> bool:
        if map_name == "?":
            return False
        if self._all_maps:
            return True
        return map_name not in self._manual_control_maps
