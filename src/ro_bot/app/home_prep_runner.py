"""Standalone loop for :class:`~ro_bot.hunt.policies.home_prep.HomePrepPolicy`.

Does not run :class:`~ro_bot.hunt.controller.HuntController` — no combat, buffs,
or farm route. Only town prep macros + optional weight wait.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from ro_bot.core.network.sniffer import PacketSniffer
from ro_bot.hunt.policies.home_prep import HomePrepPolicy

logger = logging.getLogger(__name__)

HOME_PREP_POLL_SEC = 0.05

#: DEV ``home-prep-dev``: seconds on ``home_map`` after manual ``h`` before prep.
DEFAULT_HOME_PREP_DEV_SETTLE_SEC = 3.0


def run_home_prep_loop(
    policy: HomePrepPolicy,
    sniffer: PacketSniffer,
    *,
    should_stop: Callable[[], bool],
    wait_start_deadline_sec: float = 180.0,
) -> int:
    """Drive ``policy.tick`` until the sequence finishes or the user aborts.

    Returns ``0`` on success, ``1`` on timeout (never started — wrong map /
    misconfiguration) or unexpected failure logging upstream.
    """
    wall0 = time.monotonic()
    saw_started = False
    while True:
        if should_stop():
            logger.info("Home prep: aborted by hotkey")
            return 0
        now = time.monotonic()
        current_map = sniffer.get_map_name() or "?"
        policy.tick(now, current_map)
        if policy.run_started:
            saw_started = True
        if saw_started and policy.run_finished:
            logger.info("Home prep: done")
            return 0
        if not saw_started and now - wall0 > wait_start_deadline_sec:
            logger.error(
                "Home prep: timed out waiting to start — stand on "
                "return_to_farm.home_route.home_map (town) with "
                "active_farm_map set, home_prep enabled, and non-empty steps.",
            )
            return 1
        time.sleep(HOME_PREP_POLL_SEC)


def run_home_prep_dev_loop(
    sniffer: PacketSniffer,
    *,
    home_map: str,
    active_farm_map: str,
    policy_factory: Callable[[], HomePrepPolicy | None],
    should_stop: Callable[[], bool],
    settle_after_home_sec: float = DEFAULT_HOME_PREP_DEV_SETTLE_SEC,
) -> int:
    """DEV: after manual ``h`` onto ``home_map``, wait then run prep once per visit.

    Re-arms only after leaving ``home_map`` and entering again.
    """
    hm = home_map.strip()
    farm = active_farm_map.strip()
    if not hm or not farm:
        logger.error("home-prep-dev: home_map and active_farm_map must be set")
        return 1

    prev_map: str | None = None
    arm_at: float | None = None
    policy: HomePrepPolicy | None = None

    logger.info(
        "home-prep-dev: waiting for map=%r (not farm=%r); then %.1fs settle; "
        "Numpad 0 exits",
        hm,
        farm,
        settle_after_home_sec,
    )

    while True:
        if should_stop():
            logger.info("home-prep-dev: stopped")
            return 0
        now = time.monotonic()
        m = sniffer.get_map_name() or "?"
        on_home = m == hm and m != farm

        if not on_home:
            arm_at = None
            policy = None
            prev_map = m
            time.sleep(HOME_PREP_POLL_SEC)
            continue

        if arm_at is None:
            if prev_map is None or prev_map != hm:
                arm_at = now + max(0.0, settle_after_home_sec)
                logger.info(
                    "home-prep-dev: on %s — starting prep in %.1fs",
                    hm,
                    max(0.0, settle_after_home_sec),
                )
        elif now < arm_at:
            pass
        else:
            if policy is None:
                policy = policy_factory()
                if policy is None:
                    logger.error(
                        "home-prep-dev: no home_prep steps — set "
                        "return_to_farm.active_farm_map (registry) or JSON home_prep",
                    )
                    return 1
            policy.tick(now, m)
            if policy.run_finished:
                logger.info(
                    "home-prep-dev: done — leave %s or press Numpad 0",
                    hm,
                )
                policy = None
                arm_at = None

        prev_map = m
        time.sleep(HOME_PREP_POLL_SEC)
