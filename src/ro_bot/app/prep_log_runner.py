"""Manual prep recording: log map / player cell / cursor / weight while you play.

Use lines tagged ``PREP_SNAPSHOT`` and ``PREP_EVENT`` to tune ``home_prep`` steps.
Keys are not recorded (only memory + sniffer + screen cursor).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from ro_bot.core.memory.player_state import PlayerReader, PlayerState
from ro_bot.core.network.sniffer import PacketSniffer
from ro_bot.core.window import get_cursor_pos

PREP_LOG = logging.getLogger("ro_bot.prep_log")
WORLD_POLL_SEC = 0.4


def _looks_playable_in_world(st: PlayerState, map_name: str | None) -> bool:
    if not map_name or not str(map_name).strip():
        return False
    if st.hp_max > 0 or st.weight_max > 0:
        return True
    return st.x != 0 or st.y != 0


def wait_prep_until_in_world(
    sniffer: PacketSniffer,
    player_reader: PlayerReader,
    *,
    char_name: str,
    should_stop: Callable[[], bool],
    deadline_sec: float,
    status_log: logging.Logger | None = None,
) -> bool:
    """Wait for map from sniffer + coherent player read (in-world).

    ``status_log``: if set (e.g. ``input-capture``'s file logger), ``PREP_*``
    wait lines go there; otherwise :data:`PREP_LOG` (typically ``bot.log``).
    """
    slog = status_log or PREP_LOG
    slog.info(
        "PREP_WAIT deadline_sec=%.0f — přihlas postavu „%s“, vejdi do světa; "
        "nahrávání začne až bude mapa + postava připravené. F9 zruší.",
        deadline_sec,
        char_name,
    )
    log = logging.getLogger(__name__)
    deadline = time.monotonic() + max(1.0, deadline_sec)
    while time.monotonic() < deadline:
        if should_stop():
            slog.info("PREP_WAIT_CANCELLED")
            return False
        st = player_reader.read()
        m = sniffer.get_map_name()
        if _looks_playable_in_world(st, m):
            slog.info(
                "PREP_WAIT_OK map=%s cell=(%d,%d) hp_max=%d weight_max=%d",
                m, st.x, st.y, st.hp_max, st.weight_max,
            )
            return True
        if m and m.strip():
            log.debug(
                "prep-log: waiting for player stats (map=%r cell=%d,%d)",
                m, st.x, st.y,
            )
        time.sleep(WORLD_POLL_SEC)
    slog.error(
        "PREP_WAIT_TIMEOUT — stále není mapa/stav postavy. Zkontroluj sniffer a "
        "že jsi ve hře (ne menu).",
    )
    return False


def run_prep_log_loop(
    sniffer: PacketSniffer,
    player_reader: PlayerReader,
    *,
    char_name: str,
    should_stop: Callable[[], bool],
    interval_sec: float = 0.35,
    world_ready_timeout_sec: float = 300.0,
) -> int:
    """Poll state on an interval until ``should_stop``.

    Logs ``PREP_RECORD_BEGIN``, periodic ``PREP_SNAPSHOT``, ``PREP_EVENT`` on
    map or cell edges, and ``PREP_RECORD_END``.
    """
    if interval_sec <= 0:
        interval_sec = 0.35

    if not wait_prep_until_in_world(
        sniffer,
        player_reader,
        char_name=char_name,
        should_stop=should_stop,
        deadline_sec=world_ready_timeout_sec,
    ):
        return 1

    t0 = time.monotonic()
    last_map: str | None = None
    last_cell: tuple[int, int] | None = None

    PREP_LOG.info(
        "PREP_RECORD_BEGIN interval_sec=%.3f — play manually; "
        "numpad 0 stops. Align your actions with elapsed_sec / wall time.",
        interval_sec,
    )

    try:
        while not should_stop():
            now = time.monotonic()
            elapsed = now - t0
            wall = time.strftime("%H:%M:%S")
            st = player_reader.read()
            map_name = sniffer.get_map_name() or "?"
            cx, cy = get_cursor_pos()
            cell = (st.x, st.y)

            if last_map is not None and map_name != last_map:
                PREP_LOG.info(
                    "PREP_EVENT kind=map_change elapsed_sec=%.3f wall=%s "
                    "from=%s to=%s",
                    elapsed, wall, last_map, map_name,
                )
            if (
                last_cell is not None
                and cell != last_cell
                and cell != (0, 0)
            ):
                PREP_LOG.info(
                    "PREP_EVENT kind=cell_change elapsed_sec=%.3f wall=%s "
                    "from=(%d,%d) to=(%d,%d)",
                    elapsed,
                    wall,
                    last_cell[0],
                    last_cell[1],
                    st.x,
                    st.y,
                )

            PREP_LOG.info(
                "PREP_SNAPSHOT elapsed_sec=%.3f wall=%s map=%s "
                "cell=(%d,%d) cursor_screen=(%d,%d) weight=%d weight_max=%d",
                elapsed,
                wall,
                map_name,
                st.x,
                st.y,
                cx,
                cy,
                st.weight,
                st.weight_max,
            )

            last_map = map_name
            if cell != (0, 0):
                last_cell = cell

            time.sleep(interval_sec)
    finally:
        PREP_LOG.info(
            "PREP_RECORD_END elapsed_sec=%.3f",
            time.monotonic() - t0,
        )
    return 0
