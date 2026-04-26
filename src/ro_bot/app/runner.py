"""High-level ``run_hunt_for_profile`` entry point.

Opens the DB, applies migrations, seeds defaults, loads the requested
profile, starts a :class:`BotSession`, and hands off to
:func:`run_hunt_loop`. Hotkeys are wired to Win32 ``GetAsyncKeyState``
(see :class:`HotkeyWatcher`).
"""

from __future__ import annotations

import logging

from ro_bot.app.db.connection import open_db
from ro_bot.app.db.migrations import apply_migrations
from ro_bot.app.db.seed import seed_defaults
from ro_bot.app.repositories.profile_repo import ProfileRepository
from ro_bot.app.repositories.server_repo import ServerRepository
from ro_bot.app.session import BotSession
from ro_bot.core.hotkeys import HotkeyWatcher, VirtualKey
from ro_bot.hunt.loop import run_hunt_loop

logger = logging.getLogger(__name__)


def run_hunt_for_profile(db_path: str, profile_name: str) -> int:
    """Load ``profile_name`` from ``db_path`` and run the hunt loop.

    Returns a process exit code (0 on clean stop, 1 on init failure).
    """
    conn = open_db(db_path)
    try:
        apply_migrations(conn)
        seed_defaults(conn)

        servers = ServerRepository(conn)
        profiles = ProfileRepository(conn, servers)
        profile = profiles.get_by_name(profile_name)
    finally:
        conn.close()

    logger.info(
        "Loaded profile '%s' (char='%s' server='%s')",
        profile.name, profile.char_name, profile.server.name,
    )

    session = BotSession(profile)
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
