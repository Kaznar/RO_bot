"""Default data seeded on first DB creation.

If there's no server and no profile in the DB, we insert a single
example of each so the user has something to rename / edit in DB
Browser for SQLite without writing SQL from scratch. All values are
copied from the NexusRO prototype tuning.

Running this against an already-populated DB is a no-op.
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

_DEFAULT_SERVER_NAME = "nexusro"
_DEFAULT_PROFILE_NAME = "default"


def seed_defaults(conn: sqlite3.Connection) -> None:
    """Insert a default server + profile if none exist."""
    if _has_any_server(conn) or _has_any_profile(conn):
        return

    logger.info(
        "Seeding default server '%s' + profile '%s'",
        _DEFAULT_SERVER_NAME, _DEFAULT_PROFILE_NAME,
    )
    with conn:
        server_id = _seed_server(conn)
        _seed_profile(conn, server_id)


def _has_any_server(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM server LIMIT 1").fetchone() is not None


def _has_any_profile(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM profile LIMIT 1").fetchone() is not None


def _seed_server(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        """
        INSERT INTO server (name, process_name, window_title)
        VALUES (?, ?, ?)
        """,
        (_DEFAULT_SERVER_NAME, "nexusro.exe", "NexusRO"),
    )
    server_id = int(cur.lastrowid or 0)
    conn.execute(
        """
        INSERT INTO server_projection (
            server_id, px_per_cell_x, px_per_cell_y,
            camera_offset_x, camera_offset_y
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (server_id, 42.0, 39.0, 0.0, 0.0),
    )
    _seed_dead_zones(conn, server_id)
    return server_id


def _seed_dead_zones(conn: sqlite3.Connection, server_id: int) -> None:
    """Tuned for 1600x900 NexusRO HUD (matches prototype)."""
    zones = [
        ("TL", 0, 0, 220, 70),    # HP/SP + char info panel
        ("TR", 130, 0, 150, 60),  # upper icon strip + zenny
        ("TR", 0, 120, 42, 39),   # single-cell button under items
        ("BL", 566, 91, 42, 39),  # single-cell button above chat
    ]
    conn.executemany(
        """
        INSERT INTO server_dead_zone (
            server_id, anchor, inset_x, inset_y, width, height
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [(server_id, *z) for z in zones],
    )


def _seed_profile(conn: sqlite3.Connection, server_id: int) -> None:
    cur = conn.execute(
        """
        INSERT INTO profile (name, server_id, char_name, primary_map)
        VALUES (?, ?, ?, ?)
        """,
        (_DEFAULT_PROFILE_NAME, server_id, "JoJo", "ein_fild09"),
    )
    profile_id = int(cur.lastrowid or 0)

    conn.execute(
        """
        INSERT INTO profile_engagement (profile_id) VALUES (?)
        """,
        (profile_id,),
    )
    conn.execute(
        """
        INSERT INTO profile_heal (profile_id, key, threshold_pct, cooldown_sec)
        VALUES (?, 'q', 0.30, 1.0)
        """,
        (profile_id,),
    )
    conn.execute(
        """
        INSERT INTO profile_idle_action (profile_id, key, after_sec, after_kill_sec)
        VALUES (?, 't', 10.0, 2.0)
        """,
        (profile_id,),
    )
    conn.execute(
        """
        INSERT INTO profile_escape (profile_id, key, cooldown_sec)
        VALUES (?, 't', 3.0)
        """,
        (profile_id,),
    )

    allowed = ["Muka", "Porcellio", "Metaling", "Alligator", "Myst Case"]
    dangerous = [
        "Hunter Fly", "Dragon Fly", "Garm Baby", "Knight of Windstorm",
    ]
    conn.executemany(
        """
        INSERT INTO profile_mob (profile_id, mob_name, role)
        VALUES (?, ?, 'allowed')
        """,
        [(profile_id, m) for m in allowed],
    )
    conn.executemany(
        """
        INSERT INTO profile_mob (profile_id, mob_name, role)
        VALUES (?, ?, 'dangerous')
        """,
        [(profile_id, m) for m in dangerous],
    )

    maps = ["ein_fild09", "cmd_fild01", "xmas_dun02"]
    conn.executemany(
        """
        INSERT INTO profile_map (profile_id, map_name)
        VALUES (?, ?)
        """,
        [(profile_id, m) for m in maps],
    )

    buffs = [
        (1, "f", 1800.0),
        (2, "c", 1200.0),
    ]
    conn.executemany(
        """
        INSERT INTO profile_buff (profile_id, order_index, key, interval_sec)
        VALUES (?, ?, ?, ?)
        """,
        [(profile_id, *b) for b in buffs],
    )
