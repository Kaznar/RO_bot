"""Idempotent schema migrations driven by ``PRAGMA user_version``.

Layout: each schema version is one pure SQL file loaded at import
time. ``apply_migrations(conn)`` walks from the current
``user_version`` up to the target, executing each step inside a
transaction and bumping the version on success.

For v1 there's only ``schema.sql``. Additional versions would add
``v2.sql`` etc. — append to ``_MIGRATIONS`` and bump ``LATEST_VERSION``.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from ro_bot.app.db.connection import set_user_version, user_version

logger = logging.getLogger(__name__)

_SCHEMA_DIR = Path(__file__).parent
LATEST_VERSION = 1

_MIGRATIONS: dict[int, str] = {
    1: (_SCHEMA_DIR / "schema.sql").read_text(encoding="utf-8"),
}


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Advance ``conn`` to :data:`LATEST_VERSION`.

    Each step runs inside a transaction; on failure the migration is
    rolled back and the exception propagates.
    """
    current = user_version(conn)
    if current >= LATEST_VERSION:
        logger.debug("DB already at version %d", current)
        return

    for target in range(current + 1, LATEST_VERSION + 1):
        sql = _MIGRATIONS.get(target)
        if sql is None:
            raise RuntimeError(f"Missing migration for version {target}")
        logger.info("Applying migration v%d", target)
        with conn:
            conn.executescript(sql)
            set_user_version(conn, target)
    logger.info("DB migrated to version %d", LATEST_VERSION)
