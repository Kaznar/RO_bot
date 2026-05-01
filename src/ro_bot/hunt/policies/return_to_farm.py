"""Return-to-farm-map policy.

When the sniffer reports a map change to a *neighbor* map (as listed
in :class:`ReturnToFarmConfig`), this policy assumes we wandered
through a warp by accident and walks back into the warp that returns
us to the farm map.

Mechanics:

  * Map change → if new map is a known neighbor, arm the policy with
    the matching :class:`FarmTransition` and the timestamp.
  * On each tick: wait ``settle_sec`` from arming, then aim-and-click
    at an offset from the player. The offset varies per attempt (base
    / jitter-left / jitter-right / base+1) so an imprecise warp
    location is eventually covered.
  * If after ``retry_sec`` we are still on the same neighbor map, try
    the next variant. After the 4-step sequence (or ``max_retries``,
    whichever is lower) we give up and log a warning.
  * Map change away from the armed neighbor disarms the policy. If the
    new map is itself another neighbor we simply re-arm with the new
    transition.

The controller consults :meth:`is_active` to skip targeting while a
return is in progress (we don't want to chase mobs on a map we're
trying to leave).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from ro_bot.core.memory.player_state import PlayerReader
from ro_bot.hunt.aim_service import AimService
from ro_bot.hunt.config import FarmTransition, ReturnToFarmConfig

logger = logging.getLogger("ro_bot.hunt")


# Map-grid vectors. In Ragnarok coordinates, +Y is north, +X is east.
_DIRECTION_VECTORS: dict[str, tuple[int, int]] = {
    "right": (1, 0),
    "left": (-1, 0),
    "up": (0, 1),
    "down": (0, -1),
}

VALID_DIRECTIONS = frozenset(_DIRECTION_VECTORS.keys())


# Attempt offset sequence. Each entry yields (cells_along, cells_perp),
# where "along" is multiplied by the direction vector and "perp" by
# the CCW-rotated direction (the "left" of the walking direction).
#
#   1. base        — straight ``walk_cells``
#   2. jitter_left — base + 1 cell to the left
#   3. jitter_right— base + 1 cell to the right
#   4. extended    — ``walk_cells + 1`` straight
_ATTEMPT_SEQUENCE: tuple[tuple[str, int, int], ...] = (
    ("base", 0, 0),
    ("jitter_left", 0, +1),
    ("jitter_right", 0, -1),
    ("extended", +1, 0),
)


def _perpendicular_ccw(direction: tuple[int, int]) -> tuple[int, int]:
    """Rotate a 2D vector 90° counter-clockwise (x, y) -> (-y, x)."""
    return (-direction[1], direction[0])


@dataclass
class _ActiveReturn:
    """State while we're trying to leave a neighbor map."""
    transition: FarmTransition
    armed_at: float
    last_click_at: float | None
    attempts: int


class ReturnToFarmPolicy:
    """Tick-driven walk-back-into-the-warp policy."""

    def __init__(
        self,
        cfg: ReturnToFarmConfig,
        aim: AimService,
        player_reader: PlayerReader,
    ) -> None:
        self._cfg = cfg
        self._aim = aim
        self._player_reader = player_reader
        self._by_neighbor: dict[str, FarmTransition] = {
            t.neighbor_map: t for t in cfg.transitions
        }
        self._active: _ActiveReturn | None = None
        self._given_up_on: str | None = None

    # ── Public API ──────────────────────────────────────────────────

    def is_active(self) -> bool:
        """True while we are trying to escape a neighbor map."""
        return self._active is not None

    def on_map_change(self, map_name: str, now: float) -> None:
        """Called from the controller for every map change event."""
        transition = self._by_neighbor.get(map_name)
        if transition is None:
            # Left the neighbor (either back to farm or somewhere new).
            if self._active is not None:
                logger.info(
                    "Return-to-farm: left neighbor map → '%s', disarming",
                    map_name,
                )
            self._active = None
            self._given_up_on = None
            return
        # Re-entered a neighbor we already gave up on in a previous
        # retry loop on this same map — keep quiet, stay disarmed.
        if self._given_up_on == map_name:
            return
        logger.info(
            "Return-to-farm: arrived on neighbor '%s' of farm '%s' → "
            "will walk '%s' in %.1fs",
            map_name, transition.farm_map, transition.direction,
            self._cfg.settle_sec,
        )
        self._active = _ActiveReturn(
            transition=transition,
            armed_at=now,
            last_click_at=None,
            attempts=0,
        )

    def tick(self, now: float) -> None:
        """Advance the policy. Safe to call every controller tick."""
        state = self._active
        if state is None:
            return
        if now - state.armed_at < self._cfg.settle_sec:
            return
        last = state.last_click_at
        if last is not None and now - last < self._cfg.retry_sec:
            return
        limit = min(self._cfg.max_retries, len(_ATTEMPT_SEQUENCE))
        if state.attempts >= limit:
            logger.warning(
                "Return-to-farm: gave up on neighbor '%s' after %d "
                "attempts (still there) — disarming",
                state.transition.neighbor_map, state.attempts,
            )
            self._given_up_on = state.transition.neighbor_map
            self._active = None
            return
        self._do_walk_click(state, now)

    def shift(self, delta: float) -> None:
        """Pause/resume: slide timestamps by ``delta``."""
        state = self._active
        if state is None:
            return
        state.armed_at += delta
        if state.last_click_at is not None:
            state.last_click_at += delta

    # ── Internals ───────────────────────────────────────────────────

    def _do_walk_click(self, state: _ActiveReturn, now: float) -> None:
        player = self._player_reader.read()
        if player.x == 0 and player.y == 0:
            # Memory not ready yet — retry on the next tick; don't
            # consume an attempt.
            return
        direction = _DIRECTION_VECTORS[state.transition.direction]
        perp = _perpendicular_ccw(direction)
        variant, along_bonus, perp_bonus = _ATTEMPT_SEQUENCE[state.attempts]
        walk = self._cfg.walk_cells + along_bonus
        target = (
            player.x + direction[0] * walk + perp[0] * perp_bonus,
            player.y + direction[1] * walk + perp[1] * perp_bonus,
        )
        try:
            self._aim.aim_and_click((player.x, player.y), target)
        except Exception:
            logger.exception("Return-to-farm: aim_and_click failed")
            return
        state.attempts += 1
        state.last_click_at = now
        logger.info(
            "Return-to-farm: click #%d (%s) on '%s' player=(%d,%d) "
            "target=(%d,%d) dir=%s",
            state.attempts, variant, state.transition.neighbor_map,
            player.x, player.y, target[0], target[1],
            state.transition.direction,
        )
