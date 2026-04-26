"""Arduino Pro Micro HID bridge over USB-serial.

Protocol: newline-terminated ASCII commands. Firmware responds "OK"
or "PONG". All mouse / keyboard HID events are emitted on the
Arduino side so they look identical to a real keyboard/mouse to the
game client.

Commands:
    PING        → PONG
    SC w h      → set screen dimensions (absolute positioning bound)
    MM dx dy    → relative mouse move
    MD / MU     → mouse button down / up
    KP code     → tap a key (Arduino Keyboard.h code)
"""

from __future__ import annotations

import logging
import random
import time

import serial
import serial.tools.list_ports

logger = logging.getLogger(__name__)

# Arduino Keyboard.h key codes (subset we actually use).
KEY_CODES: dict[str, int] = {
    **{c: ord(c) for c in "abcdefghijklmnopqrstuvwxyz0123456789"},
    "enter": 176, "esc": 177, "backspace": 178, "tab": 179, "space": 32,
    "up": 218, "down": 217, "left": 216, "right": 215,
    "f1": 194, "f2": 195, "f3": 196, "f4": 197,
    "f5": 198, "f6": 199, "f7": 200, "f8": 201,
    "f9": 202, "f10": 203, "f11": 204, "f12": 205,
    "shift": 129, "ctrl": 128, "alt": 130,
}


def _find_arduino_port() -> str | None:
    """Auto-detect Arduino serial port by VID:PID or description."""
    for port in serial.tools.list_ports.comports():
        desc = (port.description or "").lower()
        vid_pid = (
            f"{port.vid:04X}:{port.pid:04X}" if port.vid and port.pid else ""
        )
        logger.debug("COM port: %s — %s [%s]", port.device, desc, vid_pid)
        if "arduino" in desc or vid_pid in ("2341:8036", "2341:8037"):
            return port.device
        if "usb serial" in desc or "ch340" in desc or "cp210" in desc:
            return port.device
    return None


def _key_code(key: str) -> int:
    low = key.lower()
    if low in KEY_CODES:
        return KEY_CODES[low]
    if len(low) == 1:
        return ord(low)
    raise ValueError(f"Unknown key: {key!r}")


class ArduinoHidBridge:
    """Serial bridge to Arduino HID firmware."""

    def __init__(self, baudrate: int = 115200, timeout: float = 0.1) -> None:
        self._baudrate = baudrate
        self._timeout = timeout
        self._serial: serial.Serial | None = None

    @property
    def connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def connect(self) -> None:
        """Find port, open serial, verify firmware with PING."""
        port = _find_arduino_port()
        if port is None:
            available = [p.device for p in serial.tools.list_ports.comports()]
            raise RuntimeError(
                f"Arduino not found. Available ports: {available}",
            )

        logger.info("Opening serial on %s", port)
        self._serial = serial.Serial(
            port=port, baudrate=self._baudrate, timeout=self._timeout,
        )
        # Arduino boards reset on DTR assertion; wait for boot to settle
        # before the first request or PING might race the boot banner.
        time.sleep(2.0)
        self._serial.reset_input_buffer()

        resp = self._send("PING")
        if resp != "PONG":
            self._serial.close()
            self._serial = None
            raise RuntimeError(
                f"Arduino PING failed: expected 'PONG', got {resp!r}",
            )
        logger.info("PING/PONG OK")

    def set_screen_size(self, screen_w: int, screen_h: int) -> None:
        self._send(f"SC {screen_w} {screen_h}")
        logger.info("Screen size set to %dx%d", screen_w, screen_h)

    def move_mouse(self, dx: int, dy: int) -> None:
        self._send(f"MM {dx} {dy}")

    def mouse_click(self) -> None:
        """Left click with a randomized MD→MU delay (40–90 ms) to look
        organic to the server / any humanity heuristics."""
        self._send("MD")
        time.sleep(random.uniform(0.04, 0.09))
        self._send("MU")

    def press_key(self, key: str) -> None:
        self._send(f"KP {_key_code(key)}")

    def disconnect(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("Serial connection closed")
        self._serial = None

    def _send(self, command: str) -> str:
        if self._serial is None:
            raise RuntimeError("Arduino not connected")
        logger.debug("Sent: %s", command)
        self._serial.write(f"{command}\n".encode())
        resp = self._serial.readline().decode(errors="replace").strip()
        logger.debug("Recv: %s", resp)
        return resp
