"""Kafra warp retry when home prep finishes but map is still home_map."""

from __future__ import annotations

from unittest.mock import MagicMock

from ro_bot.hunt.config import (
    FarmHomeRouteConfig,
    FarmRouteWaypoint,
    HomePrepConfig,
    HomePrepStep,
    ReturnToFarmConfig,
)
from ro_bot.hunt.policies.home_prep import HomePrepPolicy


def _make_policy(
    *,
    steps: tuple[HomePrepStep, ...],
    retry: bool = True,
    max_retries: int = 3,
) -> HomePrepPolicy:
    rtf = ReturnToFarmConfig(
        active_farm_map="mjolnir_02",
        home_map="aldebaran",
        home_route=FarmHomeRouteConfig(
            home_map="aldebaran",
            waypoints=(
                FarmRouteWaypoint("aldebaran", 144, 109),
                FarmRouteWaypoint("mjolnir_02", 99, 351),
            ),
        ),
        home_prep=HomePrepConfig(
            enabled=True,
            steps=steps,
            retry_kafra_warp_until_farm_map=retry,
            kafra_warp_max_retries=max_retries,
        ),
    )
    bridge = MagicMock()
    player = MagicMock()
    player.read.return_value = MagicMock(x=144, y=109, weight=100, weight_max=1000)
    aim = MagicMock()
    aim.click_client_pixel.return_value = True
    policy = HomePrepPolicy(rtf, bridge, player, aim)
    policy.arm_restock()
    return policy


def _run_all_steps(policy: HomePrepPolicy, current_map: str) -> None:
    t = 0.0
    for _ in range(200):
        policy.tick(t, current_map)
        t += 0.5
        if policy.run_finished:
            break


def test_retries_kafra_warp_when_still_on_home_map() -> None:
    steps = (
        HomePrepStep(key="a", delay_after_sec=0.0),
        HomePrepStep(
            key="b",
            delay_after_sec=0.0,
            kafra_warp_retry_anchor=True,
        ),
        HomePrepStep(key="c", delay_after_sec=0.0),
    )
    policy = _make_policy(steps=steps, max_retries=3)
    bridge = policy._bridge

    _run_all_steps(policy, "aldebaran")

    assert policy.run_finished
    assert policy._kafra_warp_retries == 3
    # initial a,b,c + three replays of b,c
    assert bridge.press_key.call_count == 9


def test_skips_retry_when_already_on_farm_map() -> None:
    steps = (
        HomePrepStep(key="enter", delay_after_sec=0.0),
        HomePrepStep(
            key="enter",
            delay_after_sec=0.0,
            kafra_warp_retry_anchor=True,
        ),
    )
    policy = _make_policy(steps=steps, max_retries=3)
    policy._run_started_at = 0.0
    policy._idx = len(steps)

    assert not policy._maybe_retry_kafra_warp(1.0, "mjolnir_02")
    assert policy._kafra_warp_retries == 0


def test_aldebaran_plan_has_warp_retry_enabled() -> None:
    from ro_bot.hunt.routes.strategies.aldebaran_home_prep import home_prep_aldebaran

    prep = home_prep_aldebaran()
    assert prep.retry_kafra_warp_until_farm_map
    anchors = [s for s in prep.steps if s.kafra_warp_retry_anchor]
    assert len(anchors) == 1
    assert anchors[0].click_cell == (143, 120)
