"""Profile row → :class:`Profile` hydration.

Depends on :class:`ServerRepository` to hydrate the nested server
record (``profile.server``).
"""

from __future__ import annotations

import sqlite3

from ro_bot.app.models.profile import Profile
from ro_bot.app.repositories.server_repo import ServerRepository
from ro_bot.hunt.config import (
    BuffSpec,
    EngagementConfig,
    EscapeConfig,
    HealConfig,
    IdleActionConfig,
)


class ProfileNotFoundError(LookupError):
    pass


class ProfileRepository:
    """Read-only SQL → :class:`Profile` mapper."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        server_repo: ServerRepository,
    ) -> None:
        self._conn = conn
        self._servers = server_repo

    def get_by_name(self, name: str) -> Profile:
        row = self._conn.execute(
            """
            SELECT id, name, server_id, char_name, primary_map
            FROM profile WHERE name = ?
            """,
            (name,),
        ).fetchone()
        if row is None:
            raise ProfileNotFoundError(f"profile name={name!r}")
        return self._hydrate(row)

    def list_names(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT name FROM profile ORDER BY name",
        ).fetchall()
        return [row["name"] for row in rows]

    # ── Internals ────────────────────────────────────────────────────

    def _hydrate(self, row: sqlite3.Row) -> Profile:
        pid = int(row["id"])
        server = self._servers.get_by_id(int(row["server_id"]))
        allowed, dangerous = self._load_mobs(pid)
        return Profile(
            id=pid,
            name=row["name"],
            server=server,
            char_name=row["char_name"],
            primary_map=row["primary_map"] or "",
            allowed_mobs=allowed,
            dangerous_mobs=dangerous,
            maps=self._load_maps(pid),
            buffs=self._load_buffs(pid),
            heal=self._load_heal(pid),
            idle_action=self._load_idle(pid),
            escape=self._load_escape(pid),
            engagement=self._load_engagement(pid),
        )

    def _load_mobs(
        self, profile_id: int,
    ) -> tuple[frozenset[str], frozenset[str]]:
        rows = self._conn.execute(
            "SELECT mob_name, role FROM profile_mob WHERE profile_id = ?",
            (profile_id,),
        ).fetchall()
        allowed = {row["mob_name"] for row in rows if row["role"] == "allowed"}
        dangerous = {
            row["mob_name"] for row in rows if row["role"] == "dangerous"
        }
        return frozenset(allowed), frozenset(dangerous)

    def _load_maps(self, profile_id: int) -> frozenset[str]:
        rows = self._conn.execute(
            "SELECT map_name FROM profile_map WHERE profile_id = ?",
            (profile_id,),
        ).fetchall()
        return frozenset(row["map_name"] for row in rows)

    def _load_buffs(self, profile_id: int) -> tuple[BuffSpec, ...]:
        rows = self._conn.execute(
            """
            SELECT key, interval_sec FROM profile_buff
            WHERE profile_id = ?
            ORDER BY order_index, id
            """,
            (profile_id,),
        ).fetchall()
        return tuple(
            BuffSpec(key=row["key"], interval_sec=float(row["interval_sec"]))
            for row in rows
        )

    def _load_heal(self, profile_id: int) -> HealConfig | None:
        row = self._conn.execute(
            """
            SELECT key, threshold_pct, cooldown_sec FROM profile_heal
            WHERE profile_id = ?
            """,
            (profile_id,),
        ).fetchone()
        if row is None:
            return None
        return HealConfig(
            key=row["key"],
            threshold_pct=float(row["threshold_pct"]),
            cooldown_sec=float(row["cooldown_sec"]),
        )

    def _load_idle(self, profile_id: int) -> IdleActionConfig | None:
        row = self._conn.execute(
            """
            SELECT key, after_sec, after_kill_sec FROM profile_idle_action
            WHERE profile_id = ?
            """,
            (profile_id,),
        ).fetchone()
        if row is None:
            return None
        return IdleActionConfig(
            key=row["key"],
            after_sec=float(row["after_sec"]),
            after_kill_sec=float(row["after_kill_sec"]),
        )

    def _load_escape(self, profile_id: int) -> EscapeConfig | None:
        row = self._conn.execute(
            """
            SELECT key, cooldown_sec FROM profile_escape
            WHERE profile_id = ?
            """,
            (profile_id,),
        ).fetchone()
        if row is None:
            return None
        return EscapeConfig(
            key=row["key"],
            cooldown_sec=float(row["cooldown_sec"]),
        )

    def _load_engagement(self, profile_id: int) -> EngagementConfig:
        row = self._conn.execute(
            """
            SELECT kill_timeout_sec, blacklist_sec, reaim_click_cooldown_sec,
                   aim_settle_sec, target_settle_sec
            FROM profile_engagement WHERE profile_id = ?
            """,
            (profile_id,),
        ).fetchone()
        if row is None:
            return EngagementConfig()
        return EngagementConfig(
            kill_timeout_sec=float(row["kill_timeout_sec"]),
            blacklist_sec=float(row["blacklist_sec"]),
            reaim_click_cooldown_sec=float(row["reaim_click_cooldown_sec"]),
            aim_settle_sec=float(row["aim_settle_sec"]),
            target_settle_sec=float(row["target_settle_sec"]),
        )
