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
from ro_bot.app.config.route_library import (
    RouteLibraryError,
    compose_waypoints,
    load_route_library,
    resolve_library_path,
)
from ro_bot.app.models.profile import Profile
from ro_bot.app.models.server import Server
from ro_bot.core.projection.camera import CameraProjection
from ro_bot.hunt.config import (
    AimOffsetSpec,
    BuffSpec,
    EngagementConfig,
    EscapeConfig,
    FarmHomeRouteConfig,
    FarmRouteWaypoint,
    FarmTransition,
    HealConfig,
    HomePrepConfig,
    HomePrepStep,
    IdleActionConfig,
    OverweightConfig,
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
        config_dir=path.parent,
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


def _parse_profile(
    data: dict,
    *,
    server: Server,
    ctx: str,
    config_dir: Path,
) -> Profile:
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
        death_return=_parse_death_return(
            data.get("death_return"), f"{ctx}.death_return",
        ),
        idle_action=_parse_idle(data.get("idle_action"), f"{ctx}.idle_action"),
        overweight=_parse_overweight(
            data.get("overweight"), f"{ctx}.overweight",
        ),
        escape=_parse_escape(data.get("escape"), f"{ctx}.escape"),
        engagement=_parse_engagement(
            data.get("engagement"), f"{ctx}.engagement",
        ),
        return_to_farm=_parse_return_to_farm(
            data.get("return_to_farm"),
            f"{ctx}.return_to_farm",
            config_dir=config_dir,
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
        save_recovery_check_sec=_opt_num(
            data, "save_recovery_check_sec", ctx, default=5.0,
        ),
        save_recovery_key=_opt_str(
            data, "save_recovery_key", ctx, default="h",
        ),
    )


def _parse_death_return(data: Any, ctx: str) -> "DeathReturnConfig | None":
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ConfigError(f"{ctx}: must be a JSON object or omitted")
    if data.get("enabled") is False:
        return None
    from ro_bot.hunt.config import DeathReturnConfig

    d = DeathReturnConfig()
    sx_raw = data.get("second_delta_x_cells")
    sy_raw = data.get("second_delta_y_cells")
    if sx_raw is not None or sy_raw is not None:
        if sx_raw is None or sy_raw is None:
            raise ConfigError(
                f"{ctx}: set both second_delta_x_cells and second_delta_y_cells "
                "for a two-click death return, or omit both",
            )
        for label, raw in (
            ("second_delta_x_cells", sx_raw),
            ("second_delta_y_cells", sy_raw),
        ):
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ConfigError(
                    f"{ctx}.{label}: expected number, got {type(raw).__name__}",
                )
        second_dx = float(sx_raw)
        second_dy = float(sy_raw)
    else:
        second_dx = None
        second_dy = None

    return DeathReturnConfig(
        hp_at_most=_opt_int(data, "hp_at_most", ctx, default=d.hp_at_most),
        delta_x_cells=_opt_num(
            data, "delta_x_cells", ctx, default=d.delta_x_cells,
        ),
        delta_y_cells=_opt_num(
            data, "delta_y_cells", ctx, default=d.delta_y_cells,
        ),
        aim_settle_sec=_opt_num(
            data, "aim_settle_sec", ctx, default=d.aim_settle_sec,
        ),
        second_delta_x_cells=second_dx,
        second_delta_y_cells=second_dy,
        second_click_delay_sec=_opt_num(
            data, "second_click_delay_sec", ctx,
            default=d.second_click_delay_sec,
        ),
        town_return_retry_sec=_opt_num(
            data, "town_return_retry_sec", ctx, default=d.town_return_retry_sec,
        ),
        town_return_escape_key=_opt_str(
            data, "town_return_escape_key", ctx, default=d.town_return_escape_key,
        ),
    )


def _parse_overweight(data: Any, ctx: str) -> OverweightConfig | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ConfigError(f"{ctx}: must be a JSON object or omitted")
    defaults = OverweightConfig()
    key_raw = data.get("key", defaults.key)
    if key_raw is None or (isinstance(key_raw, str) and not key_raw.strip()):
        return None
    if not isinstance(key_raw, str):
        raise ConfigError(f"{ctx}.key: expected string")
    return OverweightConfig(
        ratio=_opt_num(data, "ratio", ctx, default=defaults.ratio),
        key=key_raw.strip(),
        press_interval_sec=_opt_num(
            data, "press_interval_sec", ctx,
            default=defaults.press_interval_sec,
        ),
    )


def _parse_idle(data: Any, ctx: str) -> IdleActionConfig | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ConfigError(f"{ctx}: must be a JSON object or omitted")
    defaults = IdleActionConfig(key="t")
    suppress_while_visible_name = defaults.suppress_while_visible_name
    if "suppress_while_visible_name" in data:
        raw = data["suppress_while_visible_name"]
        if not isinstance(raw, bool):
            raise ConfigError(
                f"{ctx}.suppress_while_visible_name: expected boolean",
            )
        suppress_while_visible_name = raw
    return IdleActionConfig(
        key=_req(data, "key", ctx, str),
        after_sec=_opt_num(data, "after_sec", ctx, default=defaults.after_sec),
        after_kill_sec=_opt_num(
            data, "after_kill_sec", ctx, default=defaults.after_kill_sec,
        ),
        suppress_while_visible_name=suppress_while_visible_name,
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


def _parse_return_to_farm(
    data: Any,
    ctx: str,
    *,
    config_dir: Path,
) -> ReturnToFarmConfig | None:
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
    active_raw = data.get("active_farm_map")
    if active_raw is None or active_raw == "":
        active_farm_map = None
    elif not isinstance(active_raw, str):
        raise ConfigError(
            f"{ctx}.active_farm_map: expected string or omitted",
        )
    else:
        active_farm_map = active_raw.strip() or None
    home_route = _parse_farm_home_route(
        data.get("home_route"),
        f"{ctx}.home_route",
        active_farm_map=active_farm_map,
        config_dir=config_dir,
    )
    if "home_navigation_enabled" in data:
        hne = data["home_navigation_enabled"]
        if not isinstance(hne, bool):
            raise ConfigError(f"{ctx}.home_navigation_enabled: expected boolean")
        home_navigation_enabled = hne
    else:
        home_navigation_enabled = defaults.home_navigation_enabled
    home_prep = _parse_home_prep(
        data.get("home_prep"), f"{ctx}.home_prep",
    )
    return ReturnToFarmConfig(
        walk_cells=_opt_int(
            data, "walk_cells", ctx, default=defaults.walk_cells,
        ),
        settle_sec=_opt_num(
            data, "settle_sec", ctx, default=defaults.settle_sec,
        ),
        post_map_change_grace_sec=_opt_num(
            data, "post_map_change_grace_sec", ctx,
            default=defaults.post_map_change_grace_sec,
        ),
        retry_sec=_opt_num(
            data, "retry_sec", ctx, default=defaults.retry_sec,
        ),
        max_retries=_opt_int(
            data, "max_retries", ctx, default=defaults.max_retries,
        ),
        transitions=transitions,
        active_farm_map=active_farm_map,
        home_route=home_route,
        home_navigation_enabled=home_navigation_enabled,
        home_prep=home_prep,
    )


def _parse_farm_home_route(
    data: Any,
    ctx: str,
    *,
    active_farm_map: str | None,
    config_dir: Path,
) -> FarmHomeRouteConfig | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ConfigError(f"{ctx}: must be a JSON object or omitted")
    home_map_raw = _req(data, "home_map", ctx, str).strip()
    if not home_map_raw:
        raise ConfigError(f"{ctx}.home_map: must be a non-empty string")
    compose_raw = data.get("compose")
    waypoints_raw = data.get("waypoints")
    has_compose = compose_raw is not None
    has_inline = waypoints_raw is not None
    if has_compose == has_inline:
        raise ConfigError(
            f"{ctx}: set exactly one of 'compose' (segment names) or "
            "'waypoints' (inline list)",
        )
    if has_compose:
        if not isinstance(compose_raw, list) or not compose_raw:
            raise ConfigError(
                f"{ctx}.compose: expected non-empty array of segment name strings",
            )
        names: list[str] = []
        for i, entry in enumerate(compose_raw):
            if not isinstance(entry, str) or not entry.strip():
                raise ConfigError(
                    f"{ctx}.compose[{i}]: expected non-empty string",
                )
            names.append(entry.strip())
        lib_rel = data.get("route_library")
        if lib_rel is not None and not isinstance(lib_rel, str):
            raise ConfigError(f"{ctx}.route_library: expected string path or omitted")
        lib_path = resolve_library_path(config_dir, lib_rel)
        try:
            library = load_route_library(lib_path, str(lib_path))
            wps = compose_waypoints(names, library, ctx)
        except RouteLibraryError as e:
            raise ConfigError(str(e)) from e
    else:
        assert waypoints_raw is not None
        if not isinstance(waypoints_raw, list) or len(waypoints_raw) < 2:
            raise ConfigError(
                f"{ctx}.waypoints: expected array with at least 2 entries",
            )
        w_ctx = f"{ctx}.waypoints"
        wps = []
        for i, entry in enumerate(waypoints_raw):
            item_ctx = f"{w_ctx}[{i}]"
            if not isinstance(entry, dict):
                raise ConfigError(f"{item_ctx}: must be a JSON object")
            m_raw = _req(entry, "map", item_ctx, str).strip()
            if not m_raw:
                raise ConfigError(f"{item_ctx}.map: must be a non-empty string")
            wps.append(FarmRouteWaypoint(
                map_name=m_raw,
                x=_req_int(entry, "x", item_ctx),
                y=_req_int(entry, "y", item_ctx),
            ))
    if len(wps) < 2:
        raise ConfigError(
            f"{ctx}: need at least 2 waypoints after "
            f"{'composition' if has_compose else 'parsing'} "
            f"(got {len(wps)})",
        )
    wp_ctx = f"{ctx}.waypoints" if has_inline else f"{ctx} (composed)"
    if wps[0].map_name != home_map_raw:
        raise ConfigError(
            f"{wp_ctx}[0].map: must equal {ctx}.home_map "
            f"({home_map_raw!r}) — got {wps[0].map_name!r}",
        )
    farm = (active_farm_map or "").strip()
    if not farm:
        raise ConfigError(
            f"{ctx}: requires profile.return_to_farm.active_farm_map "
            "when home_route is set",
        )
    if wps[-1].map_name != farm:
        raise ConfigError(
            f"{wp_ctx}[{len(wps) - 1}].map: must equal active_farm_map "
            f"({farm!r}) — got {wps[-1].map_name!r}",
        )
    if "enabled" in data:
        en_raw = data["enabled"]
        if not isinstance(en_raw, bool):
            raise ConfigError(f"{ctx}.enabled: expected boolean")
        enabled = en_raw
    else:
        enabled = True
    return FarmHomeRouteConfig(
        home_map=home_map_raw,
        waypoints=tuple(wps),
        enabled=enabled,
        click_cooldown_sec=_opt_num(
            data, "click_cooldown_sec", ctx,
            default=2.5,
        ),
        arrival_radius_cells=_opt_int(
            data, "arrival_radius_cells", ctx,
            default=2,
        ),
        stuck_no_move_timeout_sec=_opt_num(
            data, "stuck_no_move_timeout_sec", ctx,
            default=1.0,
        ),
        stuck_max_attempts_per_waypoint=_opt_int(
            data, "stuck_max_attempts_per_waypoint", ctx,
            default=24,
        ),
        post_map_change_grace_sec=_opt_num(
            data, "post_map_change_grace_sec", ctx,
            default=3.0,
        ),
        finish_on_active_farm_map=_parse_farm_home_route_finish_on_farm(
            data, ctx,
        ),
    )


def _parse_farm_home_route_finish_on_farm(data: dict, ctx: str) -> bool:
    if "finish_on_active_farm_map" not in data:
        return True
    raw = data["finish_on_active_farm_map"]
    if not isinstance(raw, bool):
        raise ConfigError(
            f"{ctx}.finish_on_active_farm_map: expected boolean",
        )
    return raw


def _parse_home_prep(data: Any, ctx: str) -> HomePrepConfig | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ConfigError(f"{ctx}: must be a JSON object or omitted")
    defaults = HomePrepConfig()
    steps = _parse_home_prep_steps(
        data.get("steps"), f"{ctx}.steps", required=True,
    )
    post_raw = data.get("post_steps")
    post_steps = (
        _parse_home_prep_steps(post_raw, f"{ctx}.post_steps", required=True)
        if post_raw is not None
        else ()
    )
    if "enabled" in data:
        en = data["enabled"]
        if not isinstance(en, bool):
            raise ConfigError(f"{ctx}.enabled: expected boolean")
        enabled = en
    else:
        enabled = defaults.enabled
    return HomePrepConfig(
        enabled=enabled,
        steps=steps,
        post_steps=post_steps,
        finish_when_weight_ratio_below=_opt_num(
            data,
            "finish_when_weight_ratio_below",
            ctx,
            default=defaults.finish_when_weight_ratio_below,
        ),
        max_total_sec=_opt_num(
            data, "max_total_sec", ctx, default=defaults.max_total_sec,
        ),
    )


def _home_prep_map_coord(value: Any, ctx: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{ctx}: expected number")
    return float(value)


def _parse_home_prep_steps(
    data: Any,
    ctx: str,
    *,
    required: bool,
) -> tuple[HomePrepStep, ...]:
    if data is None:
        if required:
            raise ConfigError(f"{ctx}: required")
        return ()
    if not isinstance(data, list):
        raise ConfigError(f"{ctx}: expected array")
    out: list[HomePrepStep] = []
    for i, entry in enumerate(data):
        item_ctx = f"{ctx}[{i}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{item_ctx}: must be a JSON object")
        key = _opt_str(entry, "key", item_ctx, default="")
        delay_after_sec = _opt_num(
            entry, "delay_after_sec", item_ctx, default=0.0,
        )
        cc_raw = entry.get("click_cell")
        click_cell: tuple[float, float] | None = None
        if cc_raw is not None:
            cc_ctx = f"{item_ctx}.click_cell"
            if isinstance(cc_raw, dict):
                click_cell = (
                    _home_prep_map_coord(cc_raw.get("x"), f"{cc_ctx}.x"),
                    _home_prep_map_coord(cc_raw.get("y"), f"{cc_ctx}.y"),
                )
            elif (
                isinstance(cc_raw, list)
                and len(cc_raw) == 2
                and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                        for v in cc_raw)
            ):
                click_cell = (
                    float(cc_raw[0]),
                    float(cc_raw[1]),
                )
            else:
                raise ConfigError(
                    f"{item_ctx}.click_cell: expected {{x,y}} or [x,y] number pair",
                )
        ccdt_raw = entry.get("click_cell_drag_to")
        click_cell_drag_to: tuple[float, float] | None = None
        if ccdt_raw is not None:
            dt_ctx = f"{item_ctx}.click_cell_drag_to"
            if isinstance(ccdt_raw, dict):
                click_cell_drag_to = (
                    _home_prep_map_coord(ccdt_raw.get("x"), f"{dt_ctx}.x"),
                    _home_prep_map_coord(ccdt_raw.get("y"), f"{dt_ctx}.y"),
                )
            elif (
                isinstance(ccdt_raw, list)
                and len(ccdt_raw) == 2
                and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                        for v in ccdt_raw)
            ):
                click_cell_drag_to = (float(ccdt_raw[0]), float(ccdt_raw[1]))
            else:
                raise ConfigError(
                    f"{item_ctx}.click_cell_drag_to: "
                    "expected {{x,y}} or [x,y] number pair",
                )
        ccdr_raw = entry.get("click_cell_drag_repeat_count")
        if ccdr_raw is None:
            click_cell_drag_repeat_count = 0
        elif isinstance(ccdr_raw, int) and not isinstance(ccdr_raw, bool):
            click_cell_drag_repeat_count = ccdr_raw
        else:
            raise ConfigError(
                f"{item_ctx}.click_cell_drag_repeat_count: expected integer",
            )
        if click_cell_drag_repeat_count < 0:
            raise ConfigError(
                f"{item_ctx}.click_cell_drag_repeat_count: must be >= 0",
            )
        click_cell_drag_repeat_interval_sec = _opt_num(
            entry,
            "click_cell_drag_repeat_interval_sec",
            item_ctx,
            default=0.25,
        )
        if click_cell_drag_repeat_count > 0:
            if click_cell is None or click_cell_drag_to is None:
                raise ConfigError(
                    f"{item_ctx}: click_cell_drag_repeat_count>0 requires "
                    "click_cell and click_cell_drag_to",
                )
        if click_cell_drag_to is not None and click_cell_drag_repeat_count <= 0:
            raise ConfigError(
                f"{item_ctx}: click_cell_drag_to requires "
                "click_cell_drag_repeat_count >= 1",
            )
        cl_raw = entry.get("click_client")
        click_client: tuple[int, int] | None = None
        if cl_raw is not None:
            if isinstance(cl_raw, dict):
                click_client = (
                    _req_int(cl_raw, "x", item_ctx + ".click_client"),
                    _req_int(cl_raw, "y", item_ctx + ".click_client"),
                )
            elif (
                isinstance(cl_raw, list)
                and len(cl_raw) == 2
                and all(isinstance(v, int) for v in cl_raw)
            ):
                click_client = (int(cl_raw[0]), int(cl_raw[1]))
            else:
                raise ConfigError(
                    f"{item_ctx}.click_client: expected {{x,y}} or [x,y] int pair",
                )
        dcl_raw = entry.get("drag_to_client")
        drag_to_client: tuple[int, int] | None = None
        if dcl_raw is not None:
            if isinstance(dcl_raw, dict):
                drag_to_client = (
                    _req_int(dcl_raw, "x", item_ctx + ".drag_to_client"),
                    _req_int(dcl_raw, "y", item_ctx + ".drag_to_client"),
                )
            elif (
                isinstance(dcl_raw, list)
                and len(dcl_raw) == 2
                and all(isinstance(v, int) for v in dcl_raw)
            ):
                drag_to_client = (int(dcl_raw[0]), int(dcl_raw[1]))
            else:
                raise ConfigError(
                    f"{item_ctx}.drag_to_client: expected {{x,y}} or [x,y] int pair",
                )
        if click_cell is not None and (
            click_client is not None or drag_to_client is not None
        ):
            raise ConfigError(
                f"{item_ctx}: use either click_cell (map) or click_client "
                "(HUD pixels), not both",
            )
        if drag_to_client is not None and click_client is None:
            raise ConfigError(
                f"{item_ctx}.drag_to_client requires click_client (drag start)",
            )
        ccdrc_raw = entry.get("click_client_drag_repeat_count")
        if ccdrc_raw is None:
            click_client_drag_repeat_count = 0
        elif isinstance(ccdrc_raw, int) and not isinstance(ccdrc_raw, bool):
            click_client_drag_repeat_count = ccdrc_raw
        else:
            raise ConfigError(
                f"{item_ctx}.click_client_drag_repeat_count: expected integer",
            )
        if click_client_drag_repeat_count < 0:
            raise ConfigError(
                f"{item_ctx}.click_client_drag_repeat_count: must be >= 0",
            )
        if click_client_drag_repeat_count > 0:
            if click_client is None or drag_to_client is None:
                raise ConfigError(
                    f"{item_ctx}: click_client_drag_repeat_count>0 requires "
                    "click_client and drag_to_client",
                )
        click_client_drag_repeat_interval_sec = _opt_num(
            entry,
            "click_client_drag_repeat_interval_sec",
            item_ctx,
            default=0.25,
        )
        mods_raw = entry.get("hold_modifiers")
        if mods_raw is None:
            hold_modifiers: tuple[str, ...] = ()
        elif isinstance(mods_raw, list):
            hold_modifiers = tuple(
                str(m).strip()
                for m in mods_raw
                if isinstance(m, str) and m.strip()
            )
        else:
            raise ConfigError(f"{item_ctx}.hold_modifiers: expected string array")
        mhc_raw = entry.get("modifier_hold_clicks")
        if mhc_raw is None:
            mhc_raw = entry.get("modifier_hold_left_clicks")
        if mhc_raw is None:
            modifier_hold_clicks = 0
        elif isinstance(mhc_raw, int) and not isinstance(mhc_raw, bool):
            modifier_hold_clicks = mhc_raw
        else:
            raise ConfigError(
                f"{item_ctx}.modifier_hold_clicks: expected integer",
            )
        if modifier_hold_clicks < 0:
            raise ConfigError(
                f"{item_ctx}.modifier_hold_clicks: must be >= 0",
            )
        if "modifier_hold_click_interval_sec" in entry:
            modifier_hold_click_interval_sec = _opt_num(
                entry,
                "modifier_hold_click_interval_sec",
                item_ctx,
                default=0.25,
            )
        elif "modifier_hold_left_click_interval_sec" in entry:
            modifier_hold_click_interval_sec = _opt_num(
                entry,
                "modifier_hold_left_click_interval_sec",
                item_ctx,
                default=0.25,
            )
        else:
            modifier_hold_click_interval_sec = 0.25
        modifier_hold_mouse_button = _opt_str(
            entry,
            "modifier_hold_mouse_button",
            item_ctx,
            default="left",
        ).lower()
        if modifier_hold_mouse_button not in ("left", "right"):
            raise ConfigError(
                f"{item_ctx}.modifier_hold_mouse_button: "
                "expected \"left\" or \"right\"",
            )
        if modifier_hold_clicks > 0:
            if not hold_modifiers:
                raise ConfigError(
                    f"{item_ctx}: modifier_hold_clicks requires "
                    "non-empty hold_modifiers",
                )
            if key:
                raise ConfigError(
                    f"{item_ctx}: modifier_hold_clicks cannot be combined "
                    "with key (use a separate step for Alt+key chords)",
                )
        if modifier_hold_clicks > 0 and (
            click_cell_drag_to is not None
            or click_cell_drag_repeat_count > 0
            or click_client_drag_repeat_count > 0
        ):
            raise ConfigError(
                f"{item_ctx}: cannot combine modifier_hold_clicks with "
                "click_cell_drag_to / click_cell_drag_repeat_count / "
                "click_client_drag_repeat_count",
            )
        dcp_raw = entry.get("dismiss_chat_probe_client")
        dismiss_chat_probe_client: tuple[int, int] | None = None
        if dcp_raw is not None:
            dcp_ctx = f"{item_ctx}.dismiss_chat_probe_client"
            if isinstance(dcp_raw, dict):
                dismiss_chat_probe_client = (
                    _req_int(dcp_raw, "x", dcp_ctx),
                    _req_int(dcp_raw, "y", dcp_ctx),
                )
            elif (
                isinstance(dcp_raw, list)
                and len(dcp_raw) == 2
                and all(isinstance(v, int) for v in dcp_raw)
            ):
                dismiss_chat_probe_client = (int(dcp_raw[0]), int(dcp_raw[1]))
            else:
                raise ConfigError(
                    f"{item_ctx}.dismiss_chat_probe_client: "
                    "expected {{x,y}} or [x,y] int pair",
                )
        dismiss_chat_min_channel = int(
            round(
                _opt_num(
                    entry,
                    "dismiss_chat_min_channel",
                    item_ctx,
                    default=228.0,
                ),
            ),
        )
        if not 0 <= dismiss_chat_min_channel <= 255:
            raise ConfigError(
                f"{item_ctx}.dismiss_chat_min_channel: must be 0..255",
            )
        dismiss_chat_key = _opt_str(
            entry, "dismiss_chat_key", item_ctx, default="escape",
        )
        out.append(
            HomePrepStep(
                key=key,
                delay_after_sec=delay_after_sec,
                click_cell=click_cell,
                click_client=click_client,
                drag_to_client=drag_to_client,
                hold_modifiers=hold_modifiers,
                modifier_hold_clicks=modifier_hold_clicks,
                modifier_hold_click_interval_sec=modifier_hold_click_interval_sec,
                modifier_hold_mouse_button=modifier_hold_mouse_button,
                click_cell_drag_to=click_cell_drag_to,
                click_cell_drag_repeat_count=click_cell_drag_repeat_count,
                click_cell_drag_repeat_interval_sec=(
                    click_cell_drag_repeat_interval_sec
                ),
                click_client_drag_repeat_count=click_client_drag_repeat_count,
                click_client_drag_repeat_interval_sec=(
                    click_client_drag_repeat_interval_sec
                ),
                dismiss_chat_probe_client=dismiss_chat_probe_client,
                dismiss_chat_min_channel=dismiss_chat_min_channel,
                dismiss_chat_key=dismiss_chat_key,
            ),
        )
    return tuple(out)


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


def _parse_optional_abandon_target_key(
    data: dict, ctx: str, *, default: str | None,
) -> str | None:
    if "abandon_target_key" not in data:
        return default
    raw = data["abandon_target_key"]
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        raise ConfigError(
            f"{ctx}.abandon_target_key: expected string or empty",
        )
    stripped = raw.strip()
    return stripped or None


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
        approach_stall_timeout_sec=_opt_num(
            data, "approach_stall_timeout_sec", ctx,
            default=defaults.approach_stall_timeout_sec,
        ),
        approach_stall_min_dist=_opt_int(
            data, "approach_stall_min_dist", ctx,
            default=defaults.approach_stall_min_dist,
        ),
        approach_stall_blacklist_sec=_opt_num(
            data, "approach_stall_blacklist_sec", ctx,
            default=defaults.approach_stall_blacklist_sec,
        ),
        ks_guard_min_dist=_opt_int(
            data, "ks_guard_min_dist", ctx,
            default=defaults.ks_guard_min_dist,
        ),
        ks_guard_min_hp_deficit=_opt_int(
            data, "ks_guard_min_hp_deficit", ctx,
            default=defaults.ks_guard_min_hp_deficit,
        ),
        ks_guard_blacklist_sec=_opt_num(
            data, "ks_guard_blacklist_sec", ctx,
            default=defaults.ks_guard_blacklist_sec,
        ),
        abandon_target_key=_parse_optional_abandon_target_key(
            data, ctx,
            default=defaults.abandon_target_key,
        ),
        stack_cell_melee_dist=_opt_int(
            data, "stack_cell_melee_dist", ctx,
            default=defaults.stack_cell_melee_dist,
        ),
        stack_cell_resume_sec=_opt_num(
            data, "stack_cell_resume_sec", ctx,
            default=defaults.stack_cell_resume_sec,
        ),
        stack_cell_warp_after_abandons=_opt_int(
            data, "stack_cell_warp_after_abandons", ctx,
            default=defaults.stack_cell_warp_after_abandons,
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


def _opt_str(data: dict, key: str, ctx: str, *, default: str) -> str:
    if key not in data:
        return default
    v = data[key]
    if not isinstance(v, str):
        raise ConfigError(f"{ctx}.{key}: expected string")
    return v


def _parse_str_list(data: list, ctx: str) -> list[str]:
    out: list[str] = []
    for i, item in enumerate(data):
        if not isinstance(item, str):
            raise ConfigError(
                f"{ctx}[{i}]: expected string, got {type(item).__name__}"
            )
        out.append(item)
    return out
