"""Named route segments for composing :class:`FarmHomeRouteConfig`.

Segments live in a JSON file next to ``config.json`` (or path given by
``home_route.route_library``). Each top-level key is a segment name; its
value is an array of ``{"map", "x", "y"}`` objects — same shape as inline
``home_route.waypoints`` entries.

The profile lists segment names in ``home_route.compose``; the loader
concatenates them (drops duplicate consecutive identical cells) and then
applies the usual first/last map validation against ``home_map`` and
``active_farm_map``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ro_bot.hunt.config import FarmRouteWaypoint

DEFAULT_ROUTE_LIBRARY_FILENAME = "route_library.json"


class RouteLibraryError(Exception):
    """Malformed segment file or unknown segment name."""


def load_route_library(path: Path, ctx: str) -> dict[str, tuple[FarmRouteWaypoint, ...]]:
    """Load segment name → waypoint tuples from JSON at ``path``."""
    if not path.is_file():
        raise RouteLibraryError(f"{ctx}: route library not found: {path}")
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise RouteLibraryError(f"{ctx}: cannot read {path} ({e})") from e
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RouteLibraryError(
            f"{ctx}: invalid JSON in {path} at line {e.lineno}: {e.msg}",
        ) from e
    if not isinstance(data, dict):
        raise RouteLibraryError(f"{ctx}: {path} top level must be a JSON object")
    out: dict[str, tuple[FarmRouteWaypoint, ...]] = {}
    for name, entry in data.items():
        if not isinstance(name, str) or not name.strip():
            raise RouteLibraryError(f"{ctx}: segment keys must be non-empty strings")
        seg_ctx = f"{ctx}[{name!r}]"
        if not isinstance(entry, list):
            raise RouteLibraryError(f"{seg_ctx}: expected JSON array of waypoints")
        wps = _parse_waypoint_objects(entry, seg_ctx)
        if len(wps) < 1:
            raise RouteLibraryError(f"{seg_ctx}: need at least one waypoint")
        out[name.strip()] = tuple(wps)
    return out


def compose_waypoints(
    segment_names: list[str],
    library: dict[str, tuple[FarmRouteWaypoint, ...]],
    ctx: str,
) -> list[FarmRouteWaypoint]:
    """Concatenate named segments and drop consecutive duplicate cells."""
    combined: list[FarmRouteWaypoint] = []
    for raw_name in segment_names:
        name = raw_name.strip()
        if not name:
            raise RouteLibraryError(f"{ctx}.compose: empty segment name")
        if name not in library:
            raise RouteLibraryError(
                f"{ctx}.compose: unknown segment {name!r} "
                f"(available: {sorted(library.keys())})",
            )
        for wp in library[name]:
            if (
                combined
                and combined[-1].map_name == wp.map_name
                and combined[-1].x == wp.x
                and combined[-1].y == wp.y
            ):
                continue
            combined.append(wp)
    return combined


def resolve_library_path(config_dir: Path, route_library: str | None) -> Path:
    """Resolve ``route_library`` relative to ``config_dir`` unless absolute."""
    name = (
        route_library.strip()
        if route_library and route_library.strip()
        else DEFAULT_ROUTE_LIBRARY_FILENAME
    )
    p = Path(name)
    if p.is_absolute():
        return p
    return config_dir / p


def _parse_waypoint_objects(
    entries: list[Any],
    ctx: str,
) -> list[FarmRouteWaypoint]:
    wps: list[FarmRouteWaypoint] = []
    for i, entry in enumerate(entries):
        item_ctx = f"{ctx}[{i}]"
        if not isinstance(entry, dict):
            raise RouteLibraryError(f"{item_ctx}: must be a JSON object")
        m_raw = entry.get("map")
        if not isinstance(m_raw, str) or not m_raw.strip():
            raise RouteLibraryError(f"{item_ctx}.map: must be a non-empty string")
        x_raw = entry.get("x")
        y_raw = entry.get("y")
        if not isinstance(x_raw, int):
            raise RouteLibraryError(f"{item_ctx}.x: expected int")
        if not isinstance(y_raw, int):
            raise RouteLibraryError(f"{item_ctx}.y: expected int")
        wps.append(FarmRouteWaypoint(map_name=m_raw.strip(), x=x_raw, y=y_raw))
    return wps
