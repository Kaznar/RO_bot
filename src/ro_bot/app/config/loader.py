"""JSON config → :class:`Profile` hydration.

Reads the config file, validates each section with explicit error
messages, and returns a fully-populated :class:`Profile` (with nested
:class:`Server`). If the file does not exist, writes defaults from
:mod:`ro_bot.app.config.defaults` and loads them — first-run seeds
``config.json`` transparently.

All validation errors raise :class:`ConfigError` with a path-qualified
message ("config.json: profile.heal.min_hp must be an int").
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ro_bot.app.config.defaults import DEFAULTS, DEFAULT_MANUAL_CONTROL_MAPS
from ro_bot.app.models.profile import Profile
from ro_bot.app.models.server import Server
from ro_bot.core.projection.camera import CameraProjection
from ro_bot.hunt.config import (
    AimOffsetSpec,
    BuffSpec,
    EngagementConfig,
    EscapeConfig,
    FarmTransition,
    HealConfig,
    IdleActionConfig,
    ReturnToFarmConfig,
)
from ro_bot.hunt.dead_zones.zone import DeadZone
from ro_bot.hunt.policies.return_to_farm import VALID_DIRECTIONS

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when the config file is missing required fields, has the
    wrong types, or cannot be parsed.
    """


def load_config(path: Path) -> Profile:
    """Load, validate, and hydrate the config at ``path``.

    Missing file → write defaults, warn, continue loading. Malformed
    JSON or failed validation → :class:`ConfigError`.
    """
    if not path.exists():
        _write_defaults(path)
        logger.warning(
            "No config found — created defaults at %s. "
            "Edit it (char_name, window_title, mobs, ...) then relaunch.",
            path,
        )

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"{path}: cannot read file ({e})") from e

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path}: invalid JSON at line {e.lineno}: {e.msg}") from e

    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a JSON object")

    ctx = str(path)
    server = _parse_server(_req(data, "server", ctx, dict), f"{ctx} [server]")
    profile = _parse_profile(
        _req(data, "profile", ctx, dict),
        server=server,
        ctx=f"{ctx} [profile]",
    )
    return profile


def _write_defaults(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(DEFAULTS, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ── Section parsers ──────────────────────────────────────────────────


def _parse_server(data: dict, ctx: str) -> Server:
    projection_data = _req(data, "projection", ctx, dict)
    dead_zones_data = _req(data, "dead_zones", ctx, list)
    return Server(
        name=_req(data, "name", ctx, str),
        process_name=_req(data, "process_name", ctx, str),
        window_title=_req(data, "window_title", ctx, str),
        projection=_parse_projection(projection_data, f"{ctx}.projection"),
        dead_zones=_parse_dead_zones(dead_zones_data, f"{ctx}.dead_zones"),
    )


def _parse_projection(data: dict, ctx: str) -> CameraProjection:
    return CameraProjection(
        px_per_cell_x=_req_num(data, "px_per_cell_x", ctx),
        px_per_cell_y=_req_num(data, "px_per_cell_y", ctx),
        camera_offset_x=_opt_num(data, "camera_offset_x", ctx, default=0.0),
        camera_offset_y=_opt_num(data, "camera_offset_y", ctx, default=0.0),
    )


def _parse_dead_zones(
    data: list, ctx: str,
) -> tuple[DeadZone, ...]:
    zones: list[DeadZone] = []
    for i, entry in enumerate(data):
        item_ctx = f"{ctx}[{i}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{item_ctx}: must be a JSON object")
        anchor = _req(entry, "anchor", item_ctx, str)
        if anchor not in ("TL", "TR", "BL", "BR"):
            raise ConfigError(
                f"{item_ctx}.anchor: must be one of TL/TR/BL/BR "
                f"(got {anchor!r})"
            )
        zones.append(DeadZone(
            anchor=anchor,
            inset_x=_req_int(entry, "inset_x", item_ctx),
            inset_y=_req_int(entry, "inset_y", item_ctx),
            width=_req_int(entry, "width", item_ctx),
            height=_req_int(entry, "height", item_ctx),
        ))
    return tuple(zones)


def _parse_profile(data: dict, *, server: Server, ctx: str) -> Profile:
    mobs = _req(data, "mobs", ctx, dict)
    allowed_mobs = _parse_str_list(
        _req(mobs, "allowed", f"{ctx}.mobs", list),
        f"{ctx}.mobs.allowed",
    )
    dangerous_mobs = _parse_str_list(
        _req(mobs, "dangerous", f"{ctx}.mobs", list),
        f"{ctx}.mobs.dangerous",
    )
    if "allowed_maps" in data:
        logger.warning(
            "%s: key 'allowed_maps' is ignored — use "
            "'manual_control_maps'.",
            ctx,
        )
    manual_raw = data.get("manual_control_maps")
    legacy_raw = data.get("consumables_blocked_maps")
    if manual_raw is not None and legacy_raw is not None:
        raise ConfigError(
            f"{ctx}: use only one of 'manual_control_maps' or "
            "'consumables_blocked_maps' (legacy alias), not both",
        )
    selected = manual_raw if manual_raw is not None else legacy_raw
    selected_key = (
        "manual_control_maps"
        if manual_raw is not None
        else "consumables_blocked_maps"
    )
    if selected is None:
        selected = DEFAULT_MANUAL_CONTROL_MAPS
        selected_key = "manual_control_maps"
    elif not isinstance(selected, list):
        raise ConfigError(
            f"{ctx}.{selected_key}: expected array or omitted",
        )
    if manual_raw is None and legacy_raw is not None:
        logger.warning(
            "%s: key 'consumables_blocked_maps' is deprecated — "
            "rename to 'manual_control_maps'",
            ctx,
        )
    manual_control_maps = frozenset(
        _parse_str_list(selected, f"{ctx}.{selected_key}"),
    )
    return Profile(
        server=server,
        char_name=_req(data, "char_name", ctx, str),
        allowed_mobs=frozenset(allowed_mobs),
        dangerous_mobs=frozenset(dangerous_mobs),
        manual_control_maps=manual_control_maps,
        aim_offsets=_parse_aim_offsets(
            data.get("aim_offsets"), f"{ctx}.aim_offsets",
        ),
        buffs=_parse_buffs(
            _req(data, "buffs", ctx, list), f"{ctx}.buffs",
        ),
        heal=_parse_heal(data.get("heal"), f"{ctx}.heal"),
        idle_action=_parse_idle(data.get("idle_action"), f"{ctx}.idle_action"),
        escape=_parse_escape(data.get("escape"), f"{ctx}.escape"),
        engagement=_parse_engagement(
            data.get("engagement"), f"{ctx}.engagement",
        ),
        return_to_farm=_parse_return_to_farm(
            data.get("return_to_farm"), f"{ctx}.return_to_farm",
        ),
    )


def _parse_buffs(data: list, ctx: str) -> tuple[BuffSpec, ...]:
    items = []
    for i, entry in enumerate(data):
        item_ctx = f"{ctx}[{i}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{item_ctx}: must be a JSON object")
        items.append((
            _req_int(entry, "order", item_ctx),
            BuffSpec(
                key=_req(entry, "key", item_ctx, str),
                interval_sec=_req_num(entry, "interval_sec", item_ctx),
            ),
        ))
    items.sort(key=lambda pair: pair[0])
    return tuple(spec for _order, spec in items)


def _parse_aim_offsets(data: Any, ctx: str) -> tuple[AimOffsetSpec, ...]:
    if data is None:
        return ()
    if not isinstance(data, list):
        raise ConfigError(f"{ctx}: must be a JSON array or omitted")
    out: list[AimOffsetSpec] = []
    seen: set[str] = set()
    for i, entry in enumerate(data):
        item_ctx = f"{ctx}[{i}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{item_ctx}: must be a JSON object")
        y_off = _req_num(entry, "y_offset_cells", item_ctx)
        names_raw = entry.get("names")
        name_single = entry.get("name")
        if names_raw is not None:
            if not isinstance(names_raw, list):
                raise ConfigError(f"{item_ctx}.names: must be a JSON array")
            group = _parse_str_list(names_raw, f"{item_ctx}.names")
            if not group:
                raise ConfigError(f"{item_ctx}.names: must be non-empty")
            for n in group:
                if n in seen:
                    raise ConfigError(
                        f"{item_ctx}.names: duplicate mob name {n!r}",
                    )
                seen.add(n)
            out.append(AimOffsetSpec(
                names=frozenset(group), y_offset_cells=y_off,
            ))
        elif name_single is not None:
            if not isinstance(name_single, str) or not name_single:
                raise ConfigError(
                    f"{item_ctx}.name: must be a non-empty string",
                )
            if name_single in seen:
                raise ConfigError(
                    f"{item_ctx}.name: duplicate mob {name_single!r}",
                )
            seen.add(name_single)
            out.append(AimOffsetSpec(
                names=frozenset((name_single,)), y_offset_cells=y_off,
            ))
        else:
            raise ConfigError(
                f"{item_ctx}: need 'names' (array) or legacy 'name' (string)",
            )
    return tuple(out)


def _parse_heal(data: Any, ctx: str) -> HealConfig | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ConfigError(f"{ctx}: must be a JSON object or omitted")
    return HealConfig(
        key=_req(data, "key", ctx, str),
        min_hp=_req_int(data, "min_hp", ctx),
        cooldown_sec=_opt_num(data, "cooldown_sec", ctx, default=1.0),
    )


def _parse_idle(data: Any, ctx: str) -> IdleActionConfig | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ConfigError(f"{ctx}: must be a JSON object or omitted")
    return IdleActionConfig(
        key=_req(data, "key", ctx, str),
        after_sec=_opt_num(data, "after_sec", ctx, default=10.0),
        after_kill_sec=_opt_num(data, "after_kill_sec", ctx, default=2.0),
    )


def _parse_escape(data: Any, ctx: str) -> EscapeConfig | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ConfigError(f"{ctx}: must be a JSON object or omitted")
    return EscapeConfig(
        key=_req(data, "key", ctx, str),
        cooldown_sec=_opt_num(data, "cooldown_sec", ctx, default=3.0),
    )


def _parse_return_to_farm(data: Any, ctx: str) -> ReturnToFarmConfig | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ConfigError(f"{ctx}: must be a JSON object or omitted")
    defaults = ReturnToFarmConfig()
    maps_data = data.get("maps")
    if maps_data is None:
        maps_data = {}
    if not isinstance(maps_data, dict):
        raise ConfigError(
            f"{ctx}.maps: expected object of "
            "{farm_map: {neighbor_map: direction}}"
        )
    transitions = _parse_farm_transitions(maps_data, f"{ctx}.maps")
    return ReturnToFarmConfig(
        walk_cells=_opt_int(
            data, "walk_cells", ctx, default=defaults.walk_cells,
        ),
        settle_sec=_opt_num(
            data, "settle_sec", ctx, default=defaults.settle_sec,
        ),
        retry_sec=_opt_num(
            data, "retry_sec", ctx, default=defaults.retry_sec,
        ),
        max_retries=_opt_int(
            data, "max_retries", ctx, default=defaults.max_retries,
        ),
        transitions=transitions,
    )


def _parse_farm_transitions(
    data: dict, ctx: str,
) -> tuple[FarmTransition, ...]:
    seen_neighbors: dict[str, str] = {}
    items: list[FarmTransition] = []
    for farm_map, neighbors in data.items():
        farm_ctx = f"{ctx}.{farm_map}"
        if not isinstance(farm_map, str) or not farm_map:
            raise ConfigError(f"{farm_ctx}: farm map key must be a non-empty string")
        if not isinstance(neighbors, dict):
            raise ConfigError(
                f"{farm_ctx}: must be an object of {{neighbor_map: direction}}"
            )
        for neighbor, direction in neighbors.items():
            n_ctx = f"{farm_ctx}.{neighbor}"
            if not isinstance(neighbor, str) or not neighbor:
                raise ConfigError(
                    f"{n_ctx}: neighbor map key must be a non-empty string"
                )
            if not isinstance(direction, str):
                raise ConfigError(
                    f"{n_ctx}: direction must be a string"
                )
            if direction not in VALID_DIRECTIONS:
                raise ConfigError(
                    f"{n_ctx}: direction must be one of "
                    f"{sorted(VALID_DIRECTIONS)} (got {direction!r})"
                )
            if neighbor in seen_neighbors:
                raise ConfigError(
                    f"{n_ctx}: neighbor '{neighbor}' already configured for "
                    f"farm map '{seen_neighbors[neighbor]}' — a neighbor can "
                    "only belong to one farm map"
                )
            seen_neighbors[neighbor] = farm_map
            items.append(FarmTransition(
                farm_map=farm_map,
                neighbor_map=neighbor,
                direction=direction,
            ))
    return tuple(items)


def _parse_engagement(data: Any, ctx: str) -> EngagementConfig:
    if data is None:
        return EngagementConfig()
    if not isinstance(data, dict):
        raise ConfigError(f"{ctx}: must be a JSON object or omitted")
    defaults = EngagementConfig()
    return EngagementConfig(
        kill_timeout_sec=_opt_num(
            data, "kill_timeout_sec", ctx, default=defaults.kill_timeout_sec,
        ),
        blacklist_sec=_opt_num(
            data, "blacklist_sec", ctx, default=defaults.blacklist_sec,
        ),
        reaim_click_cooldown_sec=_opt_num(
            data, "reaim_click_cooldown_sec", ctx,
            default=defaults.reaim_click_cooldown_sec,
        ),
        aim_settle_sec=_opt_num(
            data, "aim_settle_sec", ctx, default=defaults.aim_settle_sec,
        ),
        target_settle_sec=_opt_num(
            data, "target_settle_sec", ctx, default=defaults.target_settle_sec,
        ),
        path_stuck_min_dist=_opt_int(
            data, "path_stuck_min_dist", ctx,
            default=defaults.path_stuck_min_dist,
        ),
        path_stuck_timeout_sec=_opt_num(
            data, "path_stuck_timeout_sec", ctx,
            default=defaults.path_stuck_timeout_sec,
        ),
        path_stuck_blacklist_sec=_opt_num(
            data, "path_stuck_blacklist_sec", ctx,
            default=defaults.path_stuck_blacklist_sec,
        ),
        dead_zone_wait_sec=_opt_num(
            data, "dead_zone_wait_sec", ctx,
            default=defaults.dead_zone_wait_sec,
        ),
    )


# ── Primitive helpers ────────────────────────────────────────────────


def _req(data: dict, key: str, ctx: str, expected: type) -> Any:
    if key not in data:
        raise ConfigError(f"{ctx}: missing required field '{key}'")
    value = data[key]
    if not isinstance(value, expected):
        raise ConfigError(
            f"{ctx}.{key}: expected {expected.__name__}, got {type(value).__name__}"
        )
    return value


def _req_num(data: dict, key: str, ctx: str) -> float:
    if key not in data:
        raise ConfigError(f"{ctx}: missing required field '{key}'")
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(
            f"{ctx}.{key}: expected number, got {type(value).__name__}"
        )
    return float(value)


def _req_int(data: dict, key: str, ctx: str) -> int:
    value = _req(data, key, ctx, int)
    if isinstance(value, bool):
        raise ConfigError(f"{ctx}.{key}: expected int, got bool")
    return int(value)


def _opt_num(data: dict, key: str, ctx: str, *, default: float) -> float:
    if key not in data:
        return default
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(
            f"{ctx}.{key}: expected number, got {type(value).__name__}"
        )
    return float(value)


def _opt_int(data: dict, key: str, ctx: str, *, default: int) -> int:
    if key not in data:
        return default
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(
            f"{ctx}.{key}: expected int, got {type(value).__name__}"
        )
    return value


def _parse_str_list(data: list, ctx: str) -> list[str]:
    out: list[str] = []
    for i, item in enumerate(data):
        if not isinstance(item, str):
            raise ConfigError(
                f"{ctx}[{i}]: expected string, got {type(item).__name__}"
            )
        out.append(item)
    return out
