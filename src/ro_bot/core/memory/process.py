"""Process attach + raw ReadProcessMemory primitives.

One class: :class:`ProcessHandle`. It wraps OpenProcess, gives you
``read_bytes`` / ``read_int32`` / ``scan_bytes`` /
``scan_int32_aligned_multi``, and closes the handle on ``close``.

Keeping these primitives here (instead of inside `PlayerReader` or
`entity_scanner`) lets both consumers share one OS-level handle and
avoids duplicate Win32 boilerplate.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import struct
import time
from collections.abc import Iterator

from ro_bot.core.memory.offsets import (
    ENTITY_SCAN_MAX_ADDR,
    ENTITY_SCAN_MIN_ADDR,
    MEM_COMMIT,
    PAGE_GUARD,
    PAGE_NOACCESS,
    PROCESS_QUERY_INFORMATION,
    PROCESS_VM_READ,
    SNAPPROCESS,
)

logger = logging.getLogger(__name__)

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class _MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", ctypes.wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", ctypes.wintypes.DWORD),
        ("Protect", ctypes.wintypes.DWORD),
        ("Type", ctypes.wintypes.DWORD),
    ]


class _PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.wintypes.DWORD),
        ("cntUsage", ctypes.wintypes.DWORD),
        ("th32ProcessID", ctypes.wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", ctypes.wintypes.DWORD),
        ("cntThreads", ctypes.wintypes.DWORD),
        ("th32ParentProcessID", ctypes.wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


def find_pid(process_name: str, timeout: float = 120.0) -> int | None:
    """Wait up to `timeout` seconds for a process with the given name
    to appear. Match is substring of the executable stem (case-insensitive).
    """
    needle = process_name.lower().removesuffix(".exe")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pid = _snapshot_find_pid(needle)
        if pid is not None:
            return pid
        time.sleep(2.0)
    return None


def _snapshot_find_pid(needle: str) -> int | None:
    snap = kernel32.CreateToolhelp32Snapshot(SNAPPROCESS, 0)
    if snap == -1:
        return None
    entry = _PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(_PROCESSENTRY32)
    try:
        if not kernel32.Process32First(snap, ctypes.byref(entry)):
            return None
        while True:
            exe = entry.szExeFile.decode("utf-8", errors="replace").lower()
            if needle in exe:
                return int(entry.th32ProcessID)
            if not kernel32.Process32Next(snap, ctypes.byref(entry)):
                return None
    finally:
        kernel32.CloseHandle(snap)


class ProcessHandle:
    """Owns a Win32 process handle with read+query access.

    Not thread-safe. All reads share one handle; `close()` must be
    called exactly once to release it.
    """

    def __init__(self, handle: int) -> None:
        if not handle:
            raise ValueError("ProcessHandle requires a non-zero handle")
        self._handle = handle

    @classmethod
    def open(cls, pid: int) -> ProcessHandle | None:
        """Open a process for VM_READ + QUERY. Returns None on failure."""
        h = kernel32.OpenProcess(
            PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid,
        )
        if not h:
            logger.error("OpenProcess failed: error=%d", ctypes.get_last_error())
            return None
        return cls(h)

    @property
    def raw(self) -> int:
        return self._handle

    def close(self) -> None:
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = 0

    # ── Reads ────────────────────────────────────────────────────────

    def read_bytes(self, address: int, size: int) -> bytes | None:
        buf = ctypes.create_string_buffer(size)
        n = ctypes.c_size_t(0)
        ok = kernel32.ReadProcessMemory(
            self._handle, ctypes.c_void_p(address), buf, size, ctypes.byref(n),
        )
        if not ok or n.value == 0:
            return None
        return buf.raw[:n.value]

    def read_int32(self, address: int) -> int | None:
        data = self.read_bytes(address, 4)
        if data is None or len(data) < 4:
            return None
        return struct.unpack("<i", data)[0]

    # ── Scans ────────────────────────────────────────────────────────

    def scan_bytes(self, target: bytes) -> list[int]:
        """Scan every committed, readable user-space region for `target`.

        Use for unaligned byte sequences (e.g. character name anchor).
        For aligned int32 lookups prefer ``scan_int32_aligned_multi``.
        """
        return [
            addr for _, addr in self._iter_matches(
                [target], aligned=False, min_addr=0,
            )
        ]

    def scan_int32_aligned_multi(
        self,
        values: set[int],
        *,
        range_hint: tuple[int, int] | None = None,
    ) -> Iterator[tuple[int, int]]:
        """Single-pass heap scan for any of the given 4-byte-aligned int32s.

        Yields ``(value, address)`` for each occurrence. One walk over
        the heap covers an arbitrary number of targets — per-chunk cost
        scales with the target count (each via C-level ``bytes.find``),
        but the dominant memory-read I/O happens only once.

        ``range_hint`` clips the scan to ``[lo, hi)``. Callers use this
        once they have learned where the entity slab lives, narrowing
        a 2 GB walk into a few MB and cutting wall time by ~100×.
        Without a hint the full heap above ``ENTITY_SCAN_MIN_ADDR`` is
        scanned (cold-start behavior).
        """
        if not values:
            return
        masked = {v & 0xFFFFFFFF for v in values}
        targets = [struct.pack("<I", v) for v in masked]
        target_to_value = dict(zip(targets, masked, strict=True))
        if range_hint is not None:
            lo, hi = range_hint
        else:
            lo, hi = ENTITY_SCAN_MIN_ADDR, ENTITY_SCAN_MAX_ADDR
        for target, addr in self._iter_matches(
            targets, aligned=True, min_addr=lo, max_addr=hi,
        ):
            yield target_to_value[target], addr

    def _iter_matches(
        self,
        targets: list[bytes],
        *,
        aligned: bool,
        min_addr: int,
        max_addr: int = ENTITY_SCAN_MAX_ADDR,
    ) -> Iterator[tuple[bytes, int]]:
        """Yield ``(target, absolute_addr)`` for each occurrence of any
        of ``targets`` in readable pages within ``[min_addr, max_addr)``.

        If ``aligned`` is True, only offsets divisible by 4 are yielded
        (for int32 scans). Targets must all have equal length when used
        with aligned mode (true for our int32 case).
        """
        if not targets:
            return
        chunk_size = 0x10000
        mbi = _MEMORY_BASIC_INFORMATION()
        mbi_size = ctypes.sizeof(mbi)
        # Start at the window low bound so VirtualQueryEx skips regions
        # below it (PE / static segments etc.).
        addr = min_addr
        tail_size = max(len(t) for t in targets) - 1

        while addr < max_addr:
            ret = kernel32.VirtualQueryEx(
                self._handle, ctypes.c_void_p(addr),
                ctypes.byref(mbi), mbi_size,
            )
            if ret == 0:
                break
            base = mbi.BaseAddress or 0
            size = mbi.RegionSize

            if base >= max_addr:
                break

            if self._is_readable(mbi):
                yield from self._scan_region(
                    base, size, targets, chunk_size, aligned,
                    min_addr, max_addr, tail_size,
                )

            addr = base + size
            if addr <= base:
                break

    @staticmethod
    def _is_readable(mbi: _MEMORY_BASIC_INFORMATION) -> bool:
        return (
            mbi.State == MEM_COMMIT
            and (mbi.Protect & PAGE_NOACCESS) == 0
            and (mbi.Protect & PAGE_GUARD) == 0
        )

    def _scan_region(
        self,
        base: int,
        size: int,
        targets: list[bytes],
        chunk_size: int,
        aligned: bool,
        min_addr: int,
        max_addr: int,
        tail_size: int,
    ) -> Iterator[tuple[bytes, int]]:
        # Clip the region to the [min_addr, max_addr) window so we
        # don't read pages that fall outside the caller's range hint.
        eff_start = max(base, min_addr)
        eff_end = min(base + size, max_addr)
        if eff_start >= eff_end:
            return

        offset = eff_start - base
        end_offset = eff_end - base
        prev_tail = b""
        while offset < end_offset:
            read_size = min(chunk_size, end_offset - offset)
            data = self.read_bytes(base + offset, read_size)
            if data is None:
                prev_tail = b""
                offset += read_size
                continue

            search_data = prev_tail + data
            search_base = base + offset - len(prev_tail)

            for target in targets:
                pos = 0
                while True:
                    idx = search_data.find(target, pos)
                    if idx == -1:
                        break
                    abs_addr = search_base + idx
                    if (abs_addr >= min_addr
                            and (not aligned or abs_addr % 4 == 0)):
                        yield target, abs_addr
                    pos = idx + 1

            if len(data) >= tail_size:
                prev_tail = data[-tail_size:] if tail_size > 0 else b""
            else:
                prev_tail = data
            offset += read_size
