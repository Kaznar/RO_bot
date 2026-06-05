"""Close the game client when server staff is nearby on a hunt map.

Triggers when ``min_gid <= gid <= max_gid`` (staff band on NexusRO) or the
name matches ``name_substrings`` (e.g. ``GM Star``). High mob GIDs are
ignored. Town maps in ``manual_control_maps`` are skipped, except ``home_map``
(return-to-farm town, e.g. ``xmas``) where the guard still runs.
"""

from __future__ import annotations

import logging

from ro_bot.core.network.sniffer import EntityState, PacketSniffer
from ro_bot.core.window import request_close_game_window
from ro_bot.hunt.config import StaffGuardConfig

logger = logging.getLogger("ro_bot.hunt")


def _chebyshev(
    a: tuple[int, int],
    b: tuple[int, int],
) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _name_matches_staff(name: str, substrings: tuple[str, ...]) -> bool:
    if not name or not substrings:
        return False
    lower = name.casefold()
    return any(part.casefold() in lower for part in substrings if part)


def _gid_in_staff_band(gid: int, cfg: StaffGuardConfig) -> bool:
    return cfg.min_gid <= gid <= cfg.max_gid


def is_staff_entity(ent: EntityState, cfg: StaffGuardConfig) -> bool:
    if _gid_in_staff_band(ent.gid, cfg):
        return True
    return _name_matches_staff(ent.name, cfg.name_substrings)


class StaffGuardPolicy:
    def __init__(
        self,
        cfg: StaffGuardConfig,
        sniffer: PacketSniffer,
        manual_control_maps: frozenset[str],
        *,
        home_map: str | None = None,
        game_hwnd: int | None = None,
    ) -> None:
        self._cfg = cfg
        self._sniffer = sniffer
        self._manual_control_maps = manual_control_maps
        self._home_map = (home_map or "").strip() or None
        self._game_hwnd = game_hwnd
        self._triggered = False

    def check(
        self,
        current_map: str,
        player_cell: tuple[int, int] | None,
    ) -> bool:
        """Return True once if staff was detected and close was requested."""
        if self._triggered:
            return True
        if self._manual_control_skips_guard(current_map):
            return False
        threats = self._find_nearby_staff(player_cell)
        if not threats:
            return False
        self._triggered = True
        labels = ", ".join(
            f"{n or '?'} gid={g}@{pos}" for g, n, pos in threats
        )
        logger.critical(
            "Staff guard: %s on map=%s player=%s — closing game",
            labels, current_map, player_cell,
        )
        if self._game_hwnd is not None:
            request_close_game_window(self._game_hwnd)
        else:
            logger.error(
                "Staff guard: no game hwnd — cannot close client",
            )
        return True

    def _manual_control_skips_guard(self, current_map: str) -> bool:
        if current_map not in self._manual_control_maps:
            return False
        if self._home_map is not None and current_map == self._home_map:
            return False
        return True

    def _find_nearby_staff(
        self,
        player_cell: tuple[int, int] | None,
    ) -> list[tuple[int, str, str]]:
        out: list[tuple[int, str, str]] = []
        max_dist = self._cfg.max_distance_cells
        for ent in self._sniffer.get_all_entities():
            if not is_staff_entity(ent, self._cfg):
                continue
            pos_label = f"({ent.x},{ent.y})"
            if ent.x == 0 and ent.y == 0:
                if player_cell is None:
                    continue
                out.append((ent.gid, ent.name, "?"))
                continue
            if player_cell is None:
                out.append((ent.gid, ent.name, pos_label))
                continue
            dist = _chebyshev(player_cell, (ent.x, ent.y))
            if max_dist <= 0 or dist <= max_dist:
                out.append((ent.gid, ent.name, pos_label))
        return out
