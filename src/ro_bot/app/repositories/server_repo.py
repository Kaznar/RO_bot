"""Server row → :class:`Server` hydration."""

from __future__ import annotations

import sqlite3

from ro_bot.app.models.server import Server
from ro_bot.core.projection.camera import CameraProjection
from ro_bot.hunt.dead_zones.zone import DeadZone


class ServerNotFoundError(LookupError):
    pass


class ServerRepository:
    """Read-only SQL → dataclass mapper for ``server`` + children."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_by_id(self, server_id: int) -> Server:
        row = self._conn.execute(
            "SELECT id, name, process_name, window_title FROM server WHERE id = ?",
            (server_id,),
        ).fetchone()
        if row is None:
            raise ServerNotFoundError(f"server id={server_id}")
        return self._hydrate(row)

    def get_by_name(self, name: str) -> Server:
        row = self._conn.execute(
            "SELECT id, name, process_name, window_title FROM server WHERE name = ?",
            (name,),
        ).fetchone()
        if row is None:
            raise ServerNotFoundError(f"server name={name!r}")
        return self._hydrate(row)

    def _hydrate(self, row: sqlite3.Row) -> Server:
        server_id = int(row["id"])
        return Server(
            id=server_id,
            name=row["name"],
            process_name=row["process_name"],
            window_title=row["window_title"],
            projection=self._load_projection(server_id),
            dead_zones=self._load_dead_zones(server_id),
        )

    def _load_projection(self, server_id: int) -> CameraProjection:
        row = self._conn.execute(
            """
            SELECT px_per_cell_x, px_per_cell_y,
                   camera_offset_x, camera_offset_y
            FROM server_projection WHERE server_id = ?
            """,
            (server_id,),
        ).fetchone()
        if row is None:
            raise ServerNotFoundError(
                f"server_projection missing for server_id={server_id}",
            )
        return CameraProjection(
            px_per_cell_x=float(row["px_per_cell_x"]),
            px_per_cell_y=float(row["px_per_cell_y"]),
            camera_offset_x=float(row["camera_offset_x"]),
            camera_offset_y=float(row["camera_offset_y"]),
        )

    def _load_dead_zones(self, server_id: int) -> tuple[DeadZone, ...]:
        rows = self._conn.execute(
            """
            SELECT anchor, inset_x, inset_y, width, height
            FROM server_dead_zone WHERE server_id = ?
            ORDER BY id
            """,
            (server_id,),
        ).fetchall()
        return tuple(
            DeadZone(
                anchor=row["anchor"],
                inset_x=int(row["inset_x"]),
                inset_y=int(row["inset_y"]),
                width=int(row["width"]),
                height=int(row["height"]),
            )
            for row in rows
        )
