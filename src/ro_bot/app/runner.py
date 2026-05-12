"""High-level ``run_hunt`` entry point.

Loads the config (creating defaults on first run), starts a
:class:`BotSession`, and hands off to :func:`run_hunt_loop`. Hotkeys
are wired to Win32 ``GetAsyncKeyState`` (see :class:`HotkeyWatcher`).
"""

from __future__ import annotations

import logging
from pathlib import Path

from ro_bot.app.config import ConfigError, load_config
from ro_bot.app.home_prep_runner import run_home_prep_dev_loop, run_home_prep_loop
from ro_bot.app.input_log_runner import run_input_capture_loop
from ro_bot.app.session import BotSession
from ro_bot.core.hotkeys import HotkeyWatcher, VirtualKey
from ro_bot.hunt.loop import run_hunt_loop

logger = logging.getLogger(__name__)


def run_hunt(
    config_path: str | Path,
    *,
    hunt_all: bool = False,
    selected_mobs: list[str] | None = None,
) -> int:
    """Load the config from ``config_path`` and run the hunt loop.

    Returns a process exit code (0 on clean stop, 1 on init / config failure).
    """
    path = Path(config_path)
    try:
        profile = load_config(path)
    except ConfigError:
        logger.exception("Config load failed")
        return 1

    logger.info(
        "Loaded config from '%s' (char='%s' server='%s')",
        path, profile.char_name, profile.server.name,
    )

    session = BotSession(
        profile,
        hunt_all=hunt_all,
        selected_mobs=selected_mobs,
    )
    try:
        session.start()
    except Exception:
        logger.exception("Failed to start session")
        session.stop()
        return 1

    hotkeys = HotkeyWatcher()
    try:
        run_hunt_loop(
            session.controller,
            should_stop=lambda: hotkeys.pressed(VirtualKey.F9),
            toggle_pause=lambda: hotkeys.pressed(VirtualKey.F1),
        )
    finally:
        session.stop()
    return 0


def run_home_prep(
    config_path: str | Path,
) -> int:
    """Town prep only (no hunt loop). F9 stops."""
    path = Path(config_path)
    try:
        profile = load_config(path)
    except ConfigError:
        logger.exception("Config load failed")
        return 1

    session = BotSession(profile)
    try:
        session.start()
    except Exception:
        logger.exception("Failed to start session")
        session.stop()
        return 1

    cfg = session.hunt_config
    rtf = cfg.return_to_farm
    policy = session.make_home_prep_policy()
    if policy is None:
        if rtf is None or rtf.home_route is None:
            logger.error(
                "home-prep: need return_to_farm with home_route "
                "(active_farm_map + registry or JSON home_route).",
            )
        elif rtf.home_prep is None or not rtf.home_prep.steps:
            logger.error(
                "home-prep: need return_to_farm.home_prep with non-empty steps.",
            )
        elif not rtf.home_prep.enabled:
            logger.error(
                "home-prep: home_prep.enabled is false — set true in JSON, "
                "or run `ro-bot home-prep-dev` (ignores enabled for testing).",
            )
        else:
            logger.error("home-prep: could not build HomePrepPolicy.")
        session.stop()
        return 1

    policy.arm_restock()
    session.controller.arm_farm_home_route_after_manual_town_prep()
    hotkeys = HotkeyWatcher()
    try:
        return run_home_prep_loop(
            policy,
            session.sniffer,
            should_stop=lambda: hotkeys.pressed(VirtualKey.F9),
        )
    finally:
        session.stop()


def run_home_prep_dev(
    config_path: str | Path,
    *,
    settle_after_home_sec: float = 3.0,
) -> int:
    """DEV: manual ``h`` to town, settle, then home_prep with enabled forced on."""
    path = Path(config_path)
    try:
        profile = load_config(path)
    except ConfigError:
        logger.exception("Config load failed")
        return 1

    session = BotSession(profile)
    try:
        session.start()
    except Exception:
        logger.exception("Failed to start session")
        session.stop()
        return 1

    cfg = session.hunt_config
    rtf = cfg.return_to_farm
    if rtf is None or rtf.home_route is None:
        logger.error(
            "home-prep-dev: need return_to_farm with home_route "
            "(active_farm_map + registry or JSON).",
        )
        session.stop()
        return 1
    farm = (rtf.active_farm_map or "").strip()
    if not farm:
        logger.error("home-prep-dev: set return_to_farm.active_farm_map")
        session.stop()
        return 1
    home_map = rtf.home_route.home_map.strip()

    hotkeys = HotkeyWatcher()
    try:
        return run_home_prep_dev_loop(
            session.sniffer,
            home_map=home_map,
            active_farm_map=farm,
            policy_factory=lambda: session.make_home_prep_policy(force_enabled=True),
            should_stop=lambda: hotkeys.pressed(VirtualKey.F9),
            settle_after_home_sec=settle_after_home_sec,
            after_prep_arm=(
                lambda: session.controller.arm_farm_home_route_after_manual_town_prep()
            ),
        )
    finally:
        session.stop()


def run_input_capture(
    config_path: str | Path,
    *,
    log_path: str = "input_capture.log",
    skip_in_world_wait: bool = False,
    world_ready_timeout_sec: float = 300.0,
) -> int:
    """Log LMB / keyboard via ``pynput`` to ``log_path`` (game window filter)."""
    from ro_bot.core.logging_setup import (
        setup_input_capture_logging,
        setup_root_logging,
    )

    setup_root_logging()
    path = Path(config_path)
    try:
        profile = load_config(path)
    except ConfigError:
        logger.exception("Config load failed")
        return 1

    setup_input_capture_logging(log_path=log_path)

    session = BotSession(profile)
    try:
        session.start()
    except Exception:
        logger.exception("Failed to start session")
        session.stop()
        return 1

    hotkeys = HotkeyWatcher()
    try:
        return run_input_capture_loop(
            session.sniffer,
            session.player_reader,
            window_title_substring=profile.server.window_title,
            char_name=profile.char_name,
            should_stop=lambda: hotkeys.pressed(VirtualKey.F9),
            world_ready_timeout_sec=world_ready_timeout_sec,
            skip_in_world_wait=skip_in_world_wait,
        )
    finally:
        session.stop()
