"""Typed farm-return route built from Python segments.

Use :class:`FarmReturnPlan` in strategy modules, register factories in
``registry.py``, and let ``app.session`` merge into
:class:`ReturnToFarmConfig` when no JSON ``home_route`` is present.
"""

from __future__ import annotations

from dataclasses import dataclass

from ro_bot.hunt.config import FarmHomeRouteConfig, FarmRouteWaypoint


@dataclass(frozen=True)
class FarmReturnPlan:
    """Full home → farm click path (immutable)."""

    home_map: str
    waypoints: tuple[FarmRouteWaypoint, ...]
    enabled: bool = True
    click_cooldown_sec: float = 2.5
    arrival_radius_cells: int = 2
    stuck_no_move_timeout_sec: float = 1.0
    stuck_max_attempts_per_waypoint: int = 24
    post_map_change_grace_sec: float = 3.0

    def __post_init__(self) -> None:
        hm = self.home_map.strip()
        if not hm:
            raise ValueError("FarmReturnPlan.home_map must be non-empty")
        if len(self.waypoints) < 2:
            raise ValueError("FarmReturnPlan needs at least two waypoints")
        object.__setattr__(self, "home_map", hm)
        if self.waypoints[0].map_name != hm:
            raise ValueError(
                f"first waypoint map {self.waypoints[0].map_name!r} "
                f"must equal home_map {hm!r}",
            )

    def assert_targets_farm(self, active_farm_map: str) -> FarmReturnPlan:
        """Validate last waypoint lies on the configured active farm map."""
        farm = active_farm_map.strip()
        last = self.waypoints[-1].map_name
        if last != farm:
            raise ValueError(
                f"last waypoint map {last!r} must equal "
                f"active_farm_map {farm!r}",
            )
        return self

    def as_home_route_config(self) -> FarmHomeRouteConfig:
        return FarmHomeRouteConfig(
            home_map=self.home_map,
            waypoints=self.waypoints,
            enabled=self.enabled,
            click_cooldown_sec=self.click_cooldown_sec,
            arrival_radius_cells=self.arrival_radius_cells,
            stuck_no_move_timeout_sec=self.stuck_no_move_timeout_sec,
            stuck_max_attempts_per_waypoint=self.stuck_max_attempts_per_waypoint,
            post_map_change_grace_sec=self.post_map_change_grace_sec,
        )
