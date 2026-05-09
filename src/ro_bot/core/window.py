"""Game window detection, cursor queries, mouse-acceleration toggle.

All pure Win32 / pywin32 helpers; no focus stealing, no SendInput.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import time
from dataclasses import dataclass

import win32con
import win32gui
import win32ui

logger = logging.getLogger(__name__)

_user32 = ctypes.WinDLL("user32", use_last_error=True)

# Window classes we must not match when scanning for the game — Explorer
# and the Windows console have titles that can contain arbitrary text.
_EXCLUDE_CLASSES = {"CabinetWClass", "ExploreWClass", "ConsoleWindowClass"}


@dataclass(frozen=True)
class WindowRect:
    """Client-area rectangle in absolute screen coordinates."""
    left: int
    top: int
    width: int
    height: int


def find_game_window(title_substring: str) -> int:
    """Find a visible non-explorer window whose title contains the given
    substring (case-insensitive). Returns HWND.

    Raises RuntimeError if no match — caller is expected to retry.
    """
    results: list[int] = []

    def _callback(hwnd: int, _extra: object) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if title_substring.lower() not in title.lower():
            return
        if win32gui.GetClassName(hwnd) in _EXCLUDE_CLASSES:
            return
        results.append(hwnd)

    win32gui.EnumWindows(_callback, None)

    if not results:
        raise RuntimeError(
            f"No visible window matching '{title_substring}' found."
        )

    hwnd = results[0]
    logger.info(
        "Found window: '%s' (hwnd=0x%X)", win32gui.GetWindowText(hwnd), hwnd,
    )
    return hwnd


def wait_for_game_window(
    title_substring: str,
    timeout: float = 120.0,
    poll_sec: float = 2.0,
) -> int:
    """Poll until a visible window matching ``title_substring`` appears.

    Blocks up to ``timeout`` seconds, retrying every ``poll_sec``. Raises
    ``RuntimeError`` if the deadline passes without a match — caller
    treats that as a fatal startup error.
    """
    deadline = time.monotonic() + timeout
    logger.info(
        "Waiting for window '%s' (up to %.0fs)...", title_substring, timeout,
    )
    while True:
        try:
            return find_game_window(title_substring)
        except RuntimeError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(poll_sec)


def get_client_rect(hwnd: int) -> WindowRect:
    """Return the client area rectangle in screen coordinates."""
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    screen_left, screen_top = win32gui.ClientToScreen(hwnd, (left, top))
    rect = WindowRect(
        left=screen_left, top=screen_top,
        width=right - left, height=bottom - top,
    )
    logger.debug("Client rect: %s", rect)
    return rect


def get_cursor_pos() -> tuple[int, int]:
    """Return the current OS cursor position (screen coordinates)."""
    pt = ctypes.wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _sample_client_pixel_rgb_getpixel(
    hwnd: int,
    client_x: int,
    client_y: int,
) -> tuple[int, int, int] | None:
    hdc = win32gui.GetDC(hwnd)
    if not hdc:
        return None
    try:
        rgb = win32gui.GetPixel(hdc, client_x, client_y)
    finally:
        win32gui.ReleaseDC(hwnd, hdc)
    if rgb == -1 or rgb == 0xFFFFFFFF:
        return None
    r = rgb & 0xFF
    g = (rgb >> 8) & 0xFF
    b = (rgb >> 16) & 0xFF
    return (r, g, b)


def _sample_client_pixel_rgb_bitblt(
    hwnd: int,
    client_x: int,
    client_y: int,
) -> tuple[int, int, int] | None:
    """Copy 1×1 from the client DC via ``BitBlt`` (often sees UI where
    ``GetPixel`` returns black on GPU-presented game clients).
    """
    hdc_raw = win32gui.GetDC(hwnd)
    if not hdc_raw:
        return None
    src_dc = win32ui.CreateDCFromHandle(hdc_raw)
    mem_dc = src_dc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(src_dc, 1, 1)
    old_bmp = mem_dc.SelectObject(bmp)
    try:
        ok = mem_dc.BitBlt(
            (0, 0),
            (1, 1),
            src_dc,
            (client_x, client_y),
            win32con.SRCCOPY,
        )
        if not ok:
            return None
        bits = bmp.GetBitmapBits(True)
    finally:
        mem_dc.SelectObject(old_bmp)
        mem_dc.DeleteDC()
        bmp.DeleteObject()
        src_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hdc_raw)
    if len(bits) < 4:
        return None
    b, g, r = bits[0], bits[1], bits[2]
    return (r, g, b)


def sample_client_pixel_rgb(
    hwnd: int,
    client_x: int,
    client_y: int,
) -> tuple[int, int, int] | None:
    """Read one client pixel as ``(R, G, B)``.

    Tries ``BitBlt`` first (better for some Direct3D/OpenGL windowed clients),
    then ``GetPixel``. If both succeed, returns the sample with the higher
    ``max(R, G, B)`` so a bogus black ``GetPixel`` does not hide a bright UI.
    """
    if not hwnd or not win32gui.IsWindow(hwnd):
        return None
    try:
        blt = _sample_client_pixel_rgb_bitblt(hwnd, client_x, client_y)
    except Exception:
        logger.debug("sample_client_pixel_rgb: BitBlt failed", exc_info=True)
        blt = None
    try:
        pix = _sample_client_pixel_rgb_getpixel(hwnd, client_x, client_y)
    except Exception:
        logger.debug("sample_client_pixel_rgb: GetPixel failed", exc_info=True)
        pix = None
    if blt is None:
        return pix
    if pix is None:
        return blt
    if max(blt) >= max(pix):
        return blt
    return pix


# ── Mouse acceleration management ────────────────────────────────────

_SPI_GETMOUSE = 4
_SPI_SETMOUSE = 5


class MouseAcceleration:
    """Disable Windows mouse acceleration while the bot runs.

    Acceleration breaks relative-HID precision: equal `dx` values
    produce different pixel distances depending on how fast the
    previous move was. We save the user's original params in
    ``disable()`` and restore them in ``restore()``.

    Not thread-safe. Call from the main thread only.
    """

    def __init__(self) -> None:
        self._saved: ctypes.Array | None = None

    def disable(self) -> None:
        params = (ctypes.c_int * 3)()
        _user32.SystemParametersInfoW(
            _SPI_GETMOUSE, 0, ctypes.byref(params), 0,
        )
        self._saved = params
        logger.info(
            "Mouse acceleration saved: speed=%d threshold1=%d threshold2=%d",
            params[2], params[0], params[1],
        )
        no_accel = (ctypes.c_int * 3)(0, 0, 0)
        _user32.SystemParametersInfoW(
            _SPI_SETMOUSE, 0, ctypes.byref(no_accel), 0,
        )
        logger.info("Mouse acceleration disabled")

    def restore(self) -> None:
        if self._saved is None:
            return
        _user32.SystemParametersInfoW(
            _SPI_SETMOUSE, 0, ctypes.byref(self._saved), 0,
        )
        logger.info("Mouse acceleration restored")
        self._saved = None
