"""Logging setup: root logger for general output plus a dedicated
hunt-log file/stream for the state machine's structured events.

Kept intentionally minimal — no log rotation, no config files. Tests
run against a live game client, so logs are always wiped and inspected
after each session.
"""

from __future__ import annotations

import logging
import sys

ROOT_FORMAT = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
HUNT_FORMAT = "%(asctime)s %(levelname)-5s %(message)s"

# Channel for the hunt state machine. Separate from the root logger so
# attack/engagement events don't get buried under scapy/verbose debug.
HUNT_LOGGER_NAME = "ro_bot.hunt"


def setup_root_logging(log_path: str = "bot.log") -> None:
    """Install root file + stdout handlers once. Idempotent."""
    if getattr(setup_root_logging, "_done", False):
        return
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(ROOT_FORMAT))
    root.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(ROOT_FORMAT))
    root.addHandler(ch)

    setup_root_logging._done = True  # type: ignore[attr-defined]


def setup_hunt_logging(log_path: str = "hunt.log") -> logging.Logger:
    """Attach a dedicated file + stdout handler to the hunt logger.

    Non-propagating — hunt events do not leak into the root log.
    Idempotent; returns the configured logger.
    """
    hunt = logging.getLogger(HUNT_LOGGER_NAME)
    if getattr(setup_hunt_logging, "_done", False):
        return hunt
    hunt.setLevel(logging.DEBUG)
    hunt.propagate = False

    fmt = logging.Formatter(HUNT_FORMAT)

    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    hunt.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    hunt.addHandler(ch)

    setup_hunt_logging._done = True  # type: ignore[attr-defined]
    return hunt
