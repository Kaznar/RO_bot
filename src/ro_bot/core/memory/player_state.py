"""Player-state memory reader.

Uses the character-name string as an anchor and reads stat fields at
fixed offsets (see `MemoryOffsets`). RO keeps several copies of the
name in memory (party / friend list / stale allocations), so the
validator picks the one whose stats form a coherent player record.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from ro_bot.core.memory.offsets import MemoryOffsets
from ro_bot.core.memory.process import ProcessHandle, find_pid

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlayerState:
    """Immutable snapshot of player stats from memory."""
    x: int = 0
    y: int = 0
    hp: int = 0
    hp_max: int = 0
    sp: int = 0
    sp_max: int = 0


class PlayerReader:
    """Locates the character anchor in memory and reads player stats.

    Lifecycle::

        reader = PlayerReader("nexusro.exe", "JoJo")
        if reader.connect():
            state = reader.read()
            ...
            reader.disconnect()
    """

    def __init__(
        self,
        process_name: str,
        char_name: str,
        offsets: MemoryOffsets | None = None,
    ) -> None:
        self._process_name = process_name
        self._char_name = char_name
        self._offsets = offsets or MemoryOffsets()
        self._process: ProcessHandle | None = None
        self._anchor: int = 0

    @property
    def connected(self) -> bool:
        return self._process is not None and self._anchor != 0

    @property
    def process(self) -> ProcessHandle:
        """Borrow the underlying handle for entity scans.

        Raises if not connected — callers must ``connect()`` first.
        """
        if self._process is None:
            raise RuntimeError("PlayerReader not connected")
        return self._process

    def connect(self, wait_timeout: float = 120.0) -> bool:
        """Find PID, OpenProcess, locate a valid anchor. Blocks until
        all three succeed or the timeout elapses.
        """
        deadline = time.monotonic() + wait_timeout
        logger.info("Waiting for process '%s'...", self._process_name)

        pid = find_pid(self._process_name, timeout=wait_timeout)
        if pid is None:
            logger.error(
                "Process '%s' not found within %.0fs",
                self._process_name, wait_timeout,
            )
            return False
        logger.info("Process found: PID=%d", pid)

        process = ProcessHandle.open(pid)
        if process is None:
            return False
        self._process = process

        logger.info(
            "Waiting for character '%s' in memory (log in now)...",
            self._char_name,
        )
        while time.monotonic() < deadline:
            anchors = process.scan_bytes(self._char_name.encode("utf-8"))
            logger.debug(
                "Memory scan: %d matches for '%s'",
                len(anchors), self._char_name,
            )
            if anchors:
                anchor = self._pick_valid_anchor(anchors)
                if anchor is not None:
                    self._anchor = anchor
                    logger.info(
                        "Anchor found: 0x%08X (%d candidates tested)",
                        anchor, len(anchors),
                    )
                    return True
            time.sleep(3.0)

        logger.error(
            "Character '%s' not found within %.0fs",
            self._char_name, wait_timeout,
        )
        self.disconnect()
        return False

    def read(self) -> PlayerState:
        """Single-shot read of all player fields. Returns a zeroed
        ``PlayerState`` if the reader isn't connected or any field
        fails to read.
        """
        if not self.connected:
            return PlayerState()
        assert self._process is not None

        o = self._offsets
        a = self._anchor
        h = self._process

        px = h.read_int32(a + o.player_x)
        py = h.read_int32(a + o.player_y)
        hp = h.read_int32(a + o.hp_current)
        hp_max = h.read_int32(a + o.hp_max)
        sp = h.read_int32(a + o.sp_current)
        sp_max = h.read_int32(a + o.sp_max)

        return PlayerState(
            x=px or 0, y=py or 0,
            hp=hp or 0, hp_max=hp_max or 0,
            sp=sp or 0, sp_max=sp_max or 0,
        )

    def disconnect(self) -> None:
        if self._process is not None:
            self._process.close()
            logger.info("Memory reader closed")
        self._process = None
        self._anchor = 0

    def _pick_valid_anchor(self, anchors: list[int]) -> int | None:
        """Return the first anchor whose stats look like a real player.

        Filters on plausible coordinate ranges, HP/SP > 0, and hp ≤ hp_max.
        The first passing match wins; order is deterministic per snapshot.
        """
        o = self._offsets
        assert self._process is not None
        h = self._process
        for anchor in anchors:
            px = h.read_int32(anchor + o.player_x)
            py = h.read_int32(anchor + o.player_y)
            hp = h.read_int32(anchor + o.hp_current)
            hp_max = h.read_int32(anchor + o.hp_max)
            sp = h.read_int32(anchor + o.sp_current)
            sp_max = h.read_int32(anchor + o.sp_max)

            if any(v is None for v in (px, py, hp, hp_max, sp, sp_max)):
                continue
            if not (1 <= px <= 500 and 1 <= py <= 500):
                continue
            if not (1 <= hp <= 30_000 and 1 <= hp_max <= 30_000 and hp <= hp_max):
                continue
            if not (0 <= sp <= 30_000 and 1 <= sp_max <= 30_000):
                continue

            logger.debug(
                "Anchor 0x%08X valid: pos=(%d,%d) HP=%d/%d SP=%d/%d",
                anchor, px, py, hp, hp_max, sp, sp_max,
            )
            return anchor
        return None
