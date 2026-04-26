"""SQLite connection helpers.

Minimal wrapper — opens a connection, enables foreign keys + WAL, and
configures the row factory so callers can use name-based lookup.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def open_db(path: str | Path) -> sqlite3.Connection:
    """Open (or create) a SQLite database at ``path``.

    Enables foreign keys (off by default in SQLite) and WAL journal
    mode for concurrent read while the bot runs.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    logger.debug("Opened SQLite DB: %s", path)
    return conn


def user_version(conn: sqlite3.Connection) -> int:
    """Return the current ``PRAGMA user_version``."""
    cur = conn.execute("PRAGMA user_version")
    row = cur.fetchone()
    return int(row[0]) if row is not None else 0


def set_user_version(conn: sqlite3.Connection, version: int) -> None:
    """Set ``PRAGMA user_version`` (used by migrations)."""
    conn.execute(f"PRAGMA user_version = {int(version)}")
