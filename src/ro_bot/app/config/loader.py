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

from ro_bot.app.config.defaults import DEFAULTS
from ro_bot.app.models.profile import Profile
from ro_bot.app.models.server import Server
from ro_bot.core.projection.camera import CameraProjection
from ro_bot.hunt.config import (
    BuffSpec,
    EngagementConfig,
    EscapeConfig,
    HealConfig,
    IdleActionConfig,
)
from ro_bot.hunt.dead_zones.zone import DeadZone

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
    maps = _parse_str_list(
        _req(data, "allowed_maps", ctx, list),
        f"{ctx}.allowed_maps",
    )
    return Profile(
        server=server,
        char_name=_req(data, "char_name", ctx, str),
        allowed_mobs=frozenset(allowed_mobs),
        dangerous_mobs=frozenset(dangerous_mobs),
        maps=frozenset(maps),
        buffs=_parse_buffs(
            _req(data, "buffs", ctx, list), f"{ctx}.buffs",
        ),
        heal=_parse_heal(data.get("heal"), f"{ctx}.heal"),
        idle_action=_parse_idle(data.get("idle_action"), f"{ctx}.idle_action"),
        escape=_parse_escape(data.get("escape"), f"{ctx}.escape"),
        engagement=_parse_engagement(
            data.get("engagement"), f"{ctx}.engagement",
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
