"""High-level ``run_hunt`` entry point.

Loads the config (creating defaults on first run), starts a
:class:`BotSession`, and hands off to :func:`run_hunt_loop`. Hotkeys
are wired to Win32 ``GetAsyncKeyState`` (see :class:`HotkeyWatcher`).
"""

from __future__ import annotations

import logging
from pathlib import Path

from ro_bot.app.config import ConfigError, load_config
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
            should_stop=lambda: hotkeys.pressed(VirtualKey.KEY_0),
            toggle_pause=lambda: hotkeys.pressed(VirtualKey.KEY_P),
        )
    finally:
        session.stop()
    return 0
