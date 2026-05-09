"""Arduino Pro Micro HID bridge over USB-serial.

Protocol: newline-terminated ASCII commands. Firmware responds "OK"
or "PONG". All mouse / keyboard HID events are emitted on the
Arduino side so they look identical to a real keyboard/mouse to the
game client.

Commands:
    PING        → PONG
    SC w h      → set screen dimensions (absolute positioning bound)
    MM dx dy    → relative mouse move
    MD / MU     → left mouse button down / up
    RD / RU     → right mouse button down / up
    KP code     → tap a key (Arduino Keyboard.h code)
    KD code     → key down, KU code → key up (chords / Alt+E)

Right button: try ``RD``/``RU``, then other common serial tokens (many DIY
sketches differ). If nothing works, flash the sketch in ``firmware/README.md``.
Env ``ROBOT_ARDUINO_RIGHT_CLICK``: ``RD_RU``, ``C2``, ``C2NS``, ``MR``,
``LEGACY_FIRST`` (try one-shots before ``RD``).
"""

from __future__ import annotations

import logging
import os
import random
import time

import serial
import serial.tools.list_ports

from ro_bot.core.hid.exceptions import RightClickUnavailable

logger = logging.getLogger(__name__)

# (down_cmd, up_cmd). Extra pairs can mis-parse on unknown firmware — keep RD/RU.
_RIGHT_CLICK_PAIRS: tuple[tuple[str, str], ...] = (("RD", "RU"),)

# One-line / one-shot attempts (order: common DIY / legacy first).
_RIGHT_CLICK_ONESHOTS: tuple[str, ...] = (
    "C 2",
    "C2",
    "MR",
    "M2",
    "MC2",
    "MC 2",
    "MB2",
    "RMB",
    "RC",
    "RCLK",
    "RCLICK",
    "MOUSE2",
    "BTN2",
    "CLICK2",
    "CK2",
    "B2",
    "mouse2",
)

# Arduino Keyboard.h key codes (subset we actually use).
KEY_CODES: dict[str, int] = {
    **{c: ord(c) for c in "abcdefghijklmnopqrstuvwxyz0123456789"},
    "enter": 176, "esc": 177, "escape": 177, "backspace": 178, "tab": 179,
    "space": 32,
    "up": 218, "down": 217, "left": 216, "right": 215,
    "f1": 194, "f2": 195, "f3": 196, "f4": 197,
    "f5": 198, "f6": 199, "f7": 200, "f8": 201,
    "f9": 202, "f10": 203, "f11": 204, "f12": 205,
    "shift": 129, "ctrl": 128,
    #: Left Alt (Arduino ``KEY_LEFT_ALT`` / 0x82); alias ``lalt``.
    "alt": 130,
    "lalt": 130,
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


def _serial_bad(resp: str) -> bool:
    """True if the firmware line clearly signals failure."""
    s = (resp or "").strip().lower()
    if not s:
        return False
    return any(tok in s for tok in ("err", "fail", "unknown", "bad", "no"))


class ArduinoHidBridge:
    """Serial bridge to Arduino HID firmware."""

    def __init__(self, baudrate: int = 115200, timeout: float = 0.1) -> None:
        self._baudrate = baudrate
        self._timeout = timeout
        self._serial: serial.Serial | None = None
        #: Pinned two-phase right button, e.g. ``("RD", "RU")``.
        self._rmb_pair: tuple[str, str] | None = None
        #: Pinned one-shot serial line, e.g. ``"C 2"``.
        self._rmb_oneshot: str | None = None
        #: After discovery fails, avoid re-probing every tick / spamming serial.
        self._rmb_final_fail: bool = False

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
        self._rmb_pair = None
        self._rmb_oneshot = None
        self._rmb_final_fail = False

    def set_screen_size(self, screen_w: int, screen_h: int) -> None:
        self._send(f"SC {screen_w} {screen_h}")
        logger.info("Screen size set to %dx%d", screen_w, screen_h)

    def move_mouse(self, dx: int, dy: int) -> None:
        self._send(f"MM {dx} {dy}")

    def mouse_click(self) -> None:
        """Left click with a randomized MD→MU delay (40–90 ms) to look
        organic to the server / any humanity heuristics."""
        self.mouse_left_down()
        time.sleep(random.uniform(0.04, 0.09))
        self.mouse_left_up()

    def mouse_left_down(self) -> None:
        self._send("MD")

    def mouse_left_up(self) -> None:
        self._send("MU")

    def mouse_right_down(self) -> None:
        if self._rmb_pair is not None:
            self._send(self._rmb_pair[0])
            return
        self._send("RD")

    def mouse_right_up(self) -> None:
        if self._rmb_pair is not None:
            self._send(self._rmb_pair[1])
            return
        self._send("RU")

    def mouse_right_click(self) -> None:
        """Right click: discover serial strategy once, then replay pinned form."""
        if self._rmb_final_fail:
            raise RightClickUnavailable(
                "Arduino right-click still unavailable (cached failure).",
            )
        delay = random.uniform(0.04, 0.09)
        override = os.environ.get("ROBOT_ARDUINO_RIGHT_CLICK", "").strip().upper()

        if self._rmb_pair is not None:
            self._send(self._rmb_pair[0])
            time.sleep(delay)
            self._send(self._rmb_pair[1])
            return
        if self._rmb_oneshot is not None:
            self._send(self._rmb_oneshot)
            time.sleep(delay)
            return

        if override in ("C2", "C_2"):
            self._send("C 2")
            time.sleep(delay)
            return
        if override == "C2NS":
            self._send("C2")
            time.sleep(delay)
            return
        if override == "MR":
            self._send("MR")
            time.sleep(delay)
            return
        if override == "RD_RU":
            self._rmb_pair = ("RD", "RU")
            self._send("RD")
            time.sleep(delay)
            self._send("RU")
            return

        last_err = ""
        if override == "LEGACY_FIRST":
            for cmd in _RIGHT_CLICK_ONESHOTS:
                r = self._send(cmd)
                last_err = r
                if not _serial_bad(r):
                    self._rmb_oneshot = cmd
                    logger.info(
                        "Arduino: right mouse LEGACY_FIRST pinned to %r", cmd,
                    )
                    time.sleep(delay)
                    return
        for d_cmd, u_cmd in _RIGHT_CLICK_PAIRS:
            dr = self._send(d_cmd)
            last_err = dr
            if _serial_bad(dr):
                continue
            time.sleep(delay)
            ur = self._send(u_cmd)
            last_err = ur
            if _serial_bad(ur):
                continue
            self._rmb_pair = (d_cmd, u_cmd)
            logger.info(
                "Arduino: right mouse pinned to pair %s / %s",
                d_cmd, u_cmd,
            )
            return

        for cmd in _RIGHT_CLICK_ONESHOTS:
            r = self._send(cmd)
            last_err = r
            if not _serial_bad(r):
                self._rmb_oneshot = cmd
                logger.info(
                    "Arduino: right mouse pinned to one-shot %r (pairs failed)",
                    cmd,
                )
                time.sleep(delay)
                return

        self._rmb_final_fail = True
        raise RightClickUnavailable(
            "No right-mouse serial line worked (ERR from board on RD and on "
            "fallbacks). Alt+right-click for storage must use the same USB HID "
            "device as the keyboard — extend your Pro Micro sketch with RD/RU "
            "→ Mouse.press/release(MOUSE_RIGHT). See firmware/README.md in the "
            f"repo. Last serial response: {last_err!r}.",
        )

    def press_key(self, key: str) -> None:
        self._send(f"KP {_key_code(key)}")

    def press_key_with_modifiers(
        self,
        modifiers: tuple[str, ...],
        key: str,
    ) -> None:
        """Hold modifiers, key down/up, release modifiers (KD/KU firmware)."""
        for m in modifiers:
            self._send(f"KD {_key_code(m)}")
            time.sleep(0.012)
        time.sleep(0.02)
        code = _key_code(key)
        self._send(f"KD {code}")
        time.sleep(0.028)
        self._send(f"KU {code}")
        time.sleep(0.02)
        for m in reversed(modifiers):
            self._send(f"KU {_key_code(m)}")
            time.sleep(0.012)

    def key_down(self, key: str) -> None:
        self._send(f"KD {_key_code(key)}")

    def key_up(self, key: str) -> None:
        self._send(f"KU {_key_code(key)}")

    def disconnect(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("Serial connection closed")
        self._serial = None
        self._rmb_pair = None
        self._rmb_oneshot = None
        self._rmb_final_fail = False

    def _send(self, command: str) -> str:
        if self._serial is None:
            raise RuntimeError("Arduino not connected")
        logger.debug("Sent: %s", command)
        self._serial.write(f"{command}\n".encode())
        resp = self._serial.readline().decode(errors="replace").strip()
        logger.debug("Recv: %s", resp)
        return resp
